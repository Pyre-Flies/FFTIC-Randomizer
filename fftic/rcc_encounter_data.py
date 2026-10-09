"""Verified native ENTD records and sparse effective FFTIC encounter overrides.

The original four 40-byte-record files are read, never edited in place. Output
assets preserve every unmodified byte, while existing Nex overrides of changed
known fields are reconciled separately by the package writer.
"""
import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


ENTRY_FIELDS = {
    'Spriteset':(0,1), 'Flags1':(1,1), 'NameId':(2,1), 'Level':(3,1),
    'BirthMonth':(4,1), 'BirthDay':(5,1), 'Bravery':(6,1), 'Faith':(7,1),
    'JobUnlock':(8,1), 'JobLevel':(9,1), 'MainJob':(10,1), 'SecondarySkillset':(11,1),
    'Reaction':(12,2), 'Support':(14,2), 'Movement':(16,2),
    'Head':(18,1), 'Body':(19,1), 'Accessory':(20,1), 'RightHand':(21,1),
    'LeftHand':(22,1), 'Palette':(23,1), 'Flags2':(24,1),
    'PositionX':(25,1), 'PositionY':(26,1), 'InitialDirection':(27,1),
    'Unknown28':(28,1), 'EntryUnknown1D':(29,1), 'TrophyItemId':(30,1),
    'Gil':(31,1), 'UnitId':(32,1), 'Behavior':(35,1), 'TargetId':(36,1),
    'Unknown33':(33,2), 'Unknown37':(37,3),
}
FLAG_FIELDS = {
    'Flags1':('save_formation','test_teta','hidden_stats','load_formation',
              'join_after_event','monster','female','male'),
    'Flags2':('z1','z2','immortal','control','enemy_team','alternate_team',
              'randomly_present','always_present'),
}
RCC_NAMES = dict(zip(
    ('graphic','misc1','name','level','month','day','brave','faith','unlocked','unlocked_level',
     'job','secondary','reaction','support','movement','head','body','accessory','righthand',
     'lefthand','palette','misc2','x','y','facing','unknown28','unknown1d','trophy','gil',
     'unit_id','behavior','target_id'), ENTRY_FIELDS))
RCC_NAMES.update(unknown3='Unknown33',unknown4='Unknown37')
NEX_FIELDS = ('Spriteset','MainJob','JobUnlock','EntryUnknown1D','SecondarySkillset',
              'Reaction','Support','Movement','Head','Body','Accessory','RightHand',
              'LeftHand','InitialDirection','Level','JobLevel','Bravery','Faith',
              'PositionX','PositionY')
ENTRY_ASSETS = {n:f'fftpack/battle_entd{n}_ent.bin' for n in range(1,5)}
ENTRY_ASSETS[5] = 'fftpack/event_btlevt_bin_entrydata_add_ent.bin'


def decode_entry(raw):
    if len(raw)!=40:
        raise ValueError('An ENTD unit record must have exactly 40 bytes')
    return {field:int.from_bytes(raw[offset:offset+size],'little')
            for field,(offset,size) in ENTRY_FIELDS.items()}


def encode_entry(raw, row):
    block = bytearray(raw)
    for field,(offset,size) in ENTRY_FIELDS.items():
        value = row[field]
        if not isinstance(value,int) or not 0<=value<(1<<(8*size)):
            raise ValueError(f'Native ENTD field {field} exceeds its {size}-byte range: {value}')
        block[offset:offset+size] = value.to_bytes(size,'little')
    return bytes(block)


def get_flag(row, flag):
    for field,names in FLAG_FIELDS.items():
        if flag in names:
            return bool(row[field]&(1<<names.index(flag)))
    raise ValueError(f'Unknown native unit flag {flag}')


def set_flag(row, flag, value):
    for field,names in FLAG_FIELDS.items():
        if flag in names:
            bit = 1<<names.index(flag)
            row[field] = row[field]|bit if value else row[field]&~bit
            return
    raise ValueError(f'Unknown native unit flag {flag}')


def _effective(row, override):
    result = row.copy()
    if override.get('Disable',0):
        result['Spriteset'] = 0
        return result
    for field in ('Spriteset','MainJob'):
        if override.get(field,0)>0:
            result[field] = override[field]&255
    if override.get('JobUnlock',20)!=20:
        result['JobUnlock'] = override['JobUnlock']&255
    for field in ('Level','JobLevel'):
        if override.get(field,-1)>0:
            result[field] = override[field]&255
    for field in ('EntryUnknown1D','SecondarySkillset','Reaction','Support','Movement',
                  'Head','Body','Accessory','RightHand','LeftHand','Bravery','Faith','PositionX','PositionY'):
        if override.get(field,-1)>=0:
            maximum = 65535 if field in ('SecondarySkillset','Reaction','Support','Movement') else 255
            result[field] = override[field]&maximum
    if override.get('InitialDirection',255)!=255:
        result['InitialDirection'] = (result['InitialDirection']&128)|(override['InitialDirection']&15)
    if override.get('HigherElevation',255) in (0,1):
        result['InitialDirection'] = (result['InitialDirection']&127)|(override['HigherElevation']<<7)
    if override.get('LoadFormation',0):
        set_flag(result,'load_formation',True)
    # Unknown flag/control arrays and Present's native field are deliberately
    # retained as original Nex data; their names do not establish a byte map.
    return result


def prepare_unit_context(tables, game_dir, project_root):
    from .rcc_context import prepare_context
    if '_RCCContextInputs' not in tables:
        prepare_context(tables,game_dir,project_root)
    receipt = tables['_RCCContextInputs']
    key = hashlib.sha256(json.dumps(receipt['archive_sha256'],sort_keys=True).encode()).hexdigest()[:16]
    cache = Path(project_root)/'research/rcc-context'/key
    native, blocks = {}, {}
    extra = cache/ENTRY_ASSETS[5]
    if not extra.exists():
        from .preview import locate_cli,run_cli
        run_cli(locate_cli(project_root),['unpack','-i',Path(game_dir)/'data/enhanced/0002.pac',
                '-f',ENTRY_ASSETS[5],'-o',cache,'-g','fft'],cache/'entry-add.log')
    extra_hash = hashlib.sha256(extra.read_bytes()).hexdigest()
    expected_extra = receipt['files_sha256'].get(ENTRY_ASSETS[5])
    if expected_extra is not None and expected_extra!=extra_hash:
        raise ValueError('Additional ENTD cache changed; re-extract the context cache')
    if expected_extra is None:
        receipt['files_sha256'][ENTRY_ASSETS[5]] = extra_hash
        (cache/'inputs.json').write_text(json.dumps(receipt,indent=2)+'\n')
    for n in range(1,6):
        path = cache/ENTRY_ASSETS[n]
        block = path.read_bytes()
        expected = (77 if n==5 else 128)*16*40
        if len(block)!=expected:
            raise ValueError('Unexpected ENTD archive record count')
        blocks[n] = block
        for offset in range(0,len(block),40):
            native[((n-1)*128+offset//640,(offset%640)//40)] = decode_entry(block[offset:offset+40])
    with closing(sqlite3.connect(cache/'base.sqlite')) as con:
        con.row_factory = sqlite3.Row
        overrides = {(r['Key'],r['Key2']):dict(r) for r in con.execute('SELECT * FROM OverrideEntryData')}
        general = {r['Key']:dict(r) for r in con.execute('SELECT * FROM GeneralJob')}
    effective = {owner:_effective(row,overrides.get(owner,{})) for owner,row in native.items()}
    opening = effective[(387,0)]
    if (opening['Spriteset'],opening['MainJob'],opening['UnitId'])!=(2,2,2):
        raise ValueError('The independently verified opening ENTD anchor changed')
    tables['_RCCNativeEntryBlocks'] = blocks
    tables['_RCCNativeUnitContext'] = native
    tables['_RCCEffectiveUnitContext'] = copy.deepcopy(effective)
    tables['_RCCUnitContext'] = effective
    tables['_RCCEntryOverrides'] = overrides
    tables['_RCCGeneralJobs'] = general
    # Source make_rankings runs once before any mutation. Own this immutable
    # baseline cache in preparation, rather than mutating caller inputs during
    # randomize or recomputing thousands of encounter ranks for each adapter.
    from .rcc_units import native_rankings
    tables['_RCCUnitRankings'] = native_rankings(tables)
    tables['_RCCUnitInputs'] = dict(source=receipt,record_stride=40,units_per_entry=16,
                                   entries=589,classic_entries=512,enhanced_extra_entries=77,
                                   assets={ENTRY_ASSETS[n]:hashlib.sha256(b).hexdigest() for n,b in blocks.items()},
                                   occupied_units=sum(bool(r['Spriteset']) for r in effective.values()),
                                   unmodified_nex_fields=['Present','UnitId+characontrolid+Id','Unknown4',
                                                        'Unknown4C','Unknown54','Unknown5C','Unknown64','Unknown6C','Unknown74'])
    return tables['_RCCUnitInputs']


def emit_changed_entries(original, effective, native_blocks, overrides=None):
    """Return replacement native assets and sparse known-field Nex updates."""
    blocks = {n:bytearray(block) for n,block in native_blocks.items()}
    changed_files, nex, changes = set(), {}, []
    overrides = overrides or {}
    for owner,row in effective.items():
        old = original[owner]
        fields = {f:v for f,v in row.items() if f in ENTRY_FIELDS and v!=old[f]}
        if not fields:
            continue
        entd,slot = owner
        file_id,local = entd//128+1,entd%128
        offset = local*640+slot*40
        # Start with the untouched original record so unmodeled bytes survive.
        raw = native_blocks[file_id][offset:offset+40]
        desired = decode_entry(raw)
        desired.update(fields)
        # Applying all effective original fields would redundantly bake in
        # unchanged Nex overrides; only mutate the intended native fields.
        blocks[file_id][offset:offset+40] = encode_entry(raw,desired)
        changed_files.add(file_id)
        existing = overrides.get(owner,{})
        patch = {f:v for f,v in fields.items() if f in NEX_FIELDS and f in existing}
        if existing and 'InitialDirection' in fields:
            patch['InitialDirection'] = row['InitialDirection']&15
            patch['HigherElevation'] = int(bool(row['InitialDirection']&128))
        if existing and 'Spriteset' in fields and row['Spriteset']==0:
            patch['Disable'] = 1
        if patch:
            nex[owner] = patch
        for field,value in fields.items():
            changes.append(dict(entd=entd,slot=slot,field=field,before=old[field],after=value))
    return ({ENTRY_ASSETS[n]:bytes(blocks[n]) for n in sorted(changed_files)},nex,changes)


def commit_unit_assets(before, result):
    assets,nex,changes = emit_changed_entries(before['_RCCEffectiveUnitContext'],result['_RCCUnitContext'],
                                             before['_RCCNativeEntryBlocks'],before['_RCCEntryOverrides'])
    result['_RCCEntryAssets'] = assets
    result['_RCCEntryNexUpdates'] = nex
    result['_RCCEntryChanges'] = changes
    return dict(changed_units=len({(c['entd'],c['slot']) for c in changes}),
                changed_fields=len(changes),assets={p:hashlib.sha256(b).hexdigest() for p,b in assets.items()},
                nex_rows=len(nex))
