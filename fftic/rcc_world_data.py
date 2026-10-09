"""Verified Enhanced world tables and sparse plans for RCC r/t/c/f adapters.

No executable is written. Native tables not supported by the upstream loader
are returned as guarded runtime patches; the parent packager owns their use.
"""
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import struct

from .game import ENHANCED_SHA256, sections, unique_match


JOB_REQUIREMENT_FIELDS = (
    'Squire', 'Chemist', 'Knight', 'Archer', 'Monk', 'WhiteMage',
    'BlackMage', 'TimeMage', 'Summoner', 'Thief', 'Orator', 'Mystic',
    'Geomancer', 'Dragoon', 'Samurai', 'Ninja', 'Arithmetician', 'Bard',
    'Dancer', 'Mime', 'DarkKnight', 'OnionKnight', 'Unknown1', 'Unknown2',
)
WORLD_SPECS = {
    'JobNeedLevelData': dict(
        signature='02 00 03 33 50 53 00 00 00 00 00 00 20 33 40 00 04 00 55 00 00 00 00 00 88 33 43 33 54 53 55 00 00 00 00 00',
        stride=12, count=22, back=192),
    'MapTrapFormationData': dict(
        signature='1C 10 B8 00 F2 00 70 10 C6 00 F4 00 86 10 CE 00 FC 00 9C 10 D6 00 FD 00',
        stride=24, count=128, back=24),
    # Active scenario lookups at RVAs20DFC0/2FB881/2FBB6B use stride24 and
    # capacity0x377. Scenario0 terminates lookup:713 filled +174 empty rows.
    'Encounter': dict(
        signature='01 00 3E 00 00 33 34 00 01 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00 02 00 3E 00 00 33 34 00 01 00 00 00 00 00 00 00 01 00 03 00 81 00 00 00',
        stride=24, count=887, back=0),
    # Native pointers at raw8EAE58/8EAE60 point to VA1407AE2D0. All768
    # records have IdNumber==index; record768 starts a different table.
    'Formation': dict(
        signature='27 84 00 00 02 02 00 02 05 00 00 00 42 18 23 00 04 01 00 03 04 01 01 00 C0 F9 07 00 04 09 00 10 05 01 02 00',
        stride=12, count=768, back=0),
}


def _rva(data, raw):
    for section in sections(data):
        if section['raw'] <= raw < section['raw'] + section['rawsize']:
            return raw - section['raw'] + section['rva']
    raise ValueError('World table is outside a PE section')


def read_native_world(executable):
    """Read exact-build native data and verify independently audited anchors."""
    data = Path(executable).read_bytes()
    if hashlib.sha256(data).hexdigest() != ENHANCED_SHA256:
        raise ValueError('RCC world tables require the verified Enhanced executable')
    native, tables = {}, {}
    for name, spec in WORLD_SPECS.items():
        raw = unique_match(data, bytes.fromhex(spec['signature'])) - spec['back']
        block = data[raw:raw + spec['stride'] * spec['count']]
        if len(block) != spec['stride'] * spec['count']:
            raise ValueError('Truncated native world table: ' + name)
        native[name] = dict(raw=raw, rva=_rva(data, raw), stride=spec['stride'],
                            count=spec['count'], bytes=block,
                            sha256=hashlib.sha256(block).hexdigest())
        rows = {}
        for index in range(spec['count']):
            row = block[index * spec['stride']:(index + 1) * spec['stride']]
            if name == 'JobNeedLevelData':
                levels = [n for byte in row for n in (byte >> 4, byte & 15)]
                rows[index] = dict(zip(JOB_REQUIREMENT_FIELDS, levels))
            elif name == 'MapTrapFormationData':
                values = {}
                for slot in range(1, 5):
                    xy, flags, rare, common = struct.unpack_from('<BBHH', row, (slot - 1) * 6)
                    values.update({f'X{slot}': xy >> 4, f'Y{slot}': xy & 15,
                                   f'TrapFlags{slot}': flags,
                                   f'RareItemId{slot}': rare, f'CommonItemId{slot}': common})
                rows[index] = values
            elif name == 'Encounter':
                values = struct.unpack('<HBBB2BHHHIBHBBH', row)
                fields = ('scenario', 'map_id', 'weather', 'night', 'music1', 'music2',
                          'entd', 'grid', 'grid2', 'unknown0', 'ramza', 'next_scene',
                          'following', 'unknown1', 'event')
                values = dict(zip(fields, values))
                values['music'] = [values.pop('music1'), values.pop('music2')]
                rows[index] = values
            else:
                rows[index] = dict(zip(('bitmap', 'x', 'z', 'zero', 'orientation',
                                       'num_characters', 'map_number', 'id_number'),
                                      struct.unpack('<IBBBBBBH', row)))
        tables[name] = rows
    if tables['Encounter'][2]['entd'] != 387 or tables['Encounter'][2]['scenario'] != 3:
        raise ValueError('Native opening encounter anchor changed')
    if any(row['id_number'] != index for index, row in tables['Formation'].items()):
        raise ValueError('Native formation identities changed')
    return native, tables


def _prepare_nex(game_dir, project_root):
    from .preview import locate_cli, run_cli
    cli = locate_cli(project_root)
    sources = [Path(game_dir)/'data/enhanced/0004.pac',
               *sorted((Path(game_dir)/'data/enhanced').glob('0004.*.pac'))]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    key = hashlib.sha256((json.dumps(hashes, sort_keys=True)+'world-r-t-v3-conditionals').encode()).hexdigest()[:16]
    cache = Path(project_root)/'research/rcc-world'/key
    cache.mkdir(parents=True, exist_ok=True)
    receipt, database = cache/'inputs.json', cache/'base.sqlite'
    if receipt.exists():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        for name, digest in record['files_sha256'].items():
            if hashlib.sha256((cache/name).read_bytes()).hexdigest() != digest:
                raise ValueError('RCC world cache changed; re-extract its folder')
        record['database'] = str(database.resolve())
        return database, record
    for name in ('generaljob','battle','enhancedbattleevent','enhancedworldevent','characontrolid'):
        run_cli(cli, ['unpack', '-i', sources[0], '-f', f'nxd/{name}.nxd',
                      '-o', cache, '-g', 'fft'], cache/f'{name}.log')
    for source in sources[1:]:
        locale = source.name.split('.')[1]
        run_cli(cli, ['unpack', '-i', source, '-f', f'nxd/poachitem.{locale}.nxd',
                      '-o', cache, '-g', 'fft'], cache/f'poach-{locale}.log')
    run_cli(cli, ['nxd-to-sqlite', '-i', cache/'nxd', '-o', database, '-g', 'fft'], cache/'convert.log')
    files = [database, *sorted((cache/'nxd').glob('*.nxd'))]
    record = dict(archive_sha256=hashes,
                  database=str(database.resolve()),
                  files_sha256={p.relative_to(cache).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    receipt.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    return database, record


def prepare_world_data(tables, game_dir, project_root):
    native, rows = read_native_world(Path(game_dir)/'FFT_enhanced.exe')
    tables.setdefault('JobNeedLevelData', rows['JobNeedLevelData'])
    tables.setdefault('MapTrapFormationData', rows['MapTrapFormationData'])
    tables['_RCCNativeWorldTables'] = native
    tables['_RCCEncounters'] = rows['Encounter']
    tables['_RCCFormations'] = rows['Formation']
    database, inputs = _prepare_nex(game_dir, project_root)
    with closing(sqlite3.connect(database)) as con:
        con.row_factory = sqlite3.Row
        general = {r['Key']: dict(r) for r in con.execute('SELECT * FROM GeneralJob')}
        battle_columns = [row[1] for row in con.execute('PRAGMA table_info(Battle)')]
        if battle_columns != ['Key','DLCFlags']:
            raise ValueError('Enhanced battle metadata schema changed')
        battles = {r['Key']:dict(r) for r in con.execute('SELECT * FROM Battle')}
        from .rcc_conditionals import BATTLE_COLUMNS, WORLD_COLUMNS
        conditionals = {}
        for table,columns,array in (('EnhancedBattleEvent',BATTLE_COLUMNS,'Unknown14'),
                                    ('EnhancedWorldEvent',WORLD_COLUMNS,'Unknown8')):
            if tuple(row[1] for row in con.execute('PRAGMA table_info('+table+')'))!=columns:
                raise ValueError('Enhanced conditional Nex schema changed: '+table)
            conditionals[table] = {tuple(r[key] for key in ('Key','Key2','Key3')):dict(r)
                                   for r in con.execute('SELECT * FROM '+table)}
            for row in conditionals[table].values(): row[array] = json.loads(row[array])
        controls = {r['Key']:dict(r) for r in con.execute('SELECT * FROM CharaControlId')}
        for row in general.values():
            for field in ('RequiredJobExp', 'RequiredJobIds', 'RequiredJobLevels', 'RequiredJobPositions'):
                row[field] = json.loads(row[field])
        poach_tables = {r[0]: {p['Key']: dict(p) for p in con.execute('SELECT * FROM "'+r[0]+'"')}
                        for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'PoachItem-%'").fetchall()}
    if len(poach_tables) != 7 or set(general) != set(range(21)):
        raise ValueError('Original Enhanced world Nex table inventory changed')
    baseline = poach_tables['PoachItem-en']
    poaches = {}
    for monster in range(48):
        # Carcass keys follow the Enhanced UI sorting order, which differs
        # from native job94..141/RCC's monster order. IconId is the original
        # native monster index+1: Bomb6 uses carcass keys25/26, not13/14.
        common_keys = [key for key, row in baseline.items() if row['IconId'] == monster+1 and row['IsRare'] == 0]
        rare_keys = [key for key, row in baseline.items() if row['IconId'] == monster+1 and row['IsRare'] == 1]
        if len(common_keys) != 1 or len(rare_keys) != 1:
            raise ValueError('Enhanced poach pairing changed')
        common_key, rare_key = common_keys[0], rare_keys[0]
        common, rare = baseline[common_key], baseline[rare_key]
        for localized in poach_tables.values():
            if any(localized[key]['Unknown2C'] != baseline[key]['Unknown2C'] for key in (common_key, rare_key)):
                raise ValueError('Localized poach rewards disagree')
        poaches[monster] = dict(common=common['Unknown2C'], rare=rare['Unknown2C'],
                                common_key=common_key, rare_key=rare_key)
    tables['_RCCGeneralJobs'] = general
    tables['_RCCBattleMetadata'] = battles
    tables['_RCCBattleConditions'] = conditionals['EnhancedBattleEvent']
    tables['_RCCWorldConditions'] = conditionals['EnhancedWorldEvent']
    tables['_RCCCharaControls'] = controls
    tables['_RCCPoaches'] = poaches
    tables['_RCCPoachNexTables'] = poach_tables
    tables['_RCCWorldInputs'] = inputs
    return inputs


def world_nex_update(result, table, key, fields):
    result.setdefault('_RCCWorldNexUpdates', {}).setdefault(table, {}).setdefault(tuple(key), {}).update(copy.deepcopy(fields))


def commit_world_patches(before, result):
    """Encode only source Encounter/Formation fields into guarded table plans."""
    plans = result.setdefault('_RCCNativeTablePatches', [])
    for name, private in (('Encounter', '_RCCEncounters'), ('Formation', '_RCCFormations')):
        spec = before['_RCCNativeWorldTables'][name]
        block = bytearray(spec['bytes'])
        for index, row in result[private].items():
            if row == before[private][index]:
                continue
            if name == 'Encounter':
                values = [row[f] for f in ('scenario', 'map_id', 'weather', 'night')]
                values += list(row['music'])
                values += [row[f] for f in ('entd', 'grid', 'grid2', 'unknown0', 'ramza', 'next_scene', 'following', 'unknown1', 'event')]
                encoded = struct.pack('<HBBB2BHHHIBHBBH', *values)
            else:
                encoded = struct.pack('<IBBBBBBH', *[row[f] for f in ('bitmap', 'x', 'z', 'zero', 'orientation', 'num_characters', 'map_number', 'id_number')])
            block[index*spec['stride']:(index+1)*spec['stride']] = encoded
        if block != spec['bytes']:
            if any(plan['name'] == name for plan in plans):
                raise ValueError('A native world table was committed more than once')
            plans.append(dict(name=name, rva=spec['rva'], expected=spec['bytes'], data=bytes(block)))
    return plans
