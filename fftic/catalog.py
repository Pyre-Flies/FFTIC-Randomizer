"""Complete local ability inventory, with native categories and job provenance."""
from collections import defaultdict
from contextlib import closing
import copy
import csv
import json
import re
import sqlite3
from .game import JOB_FIELDS

CATEGORIES = {0:'unused',1:'action',2:'item',3:'throw',4:'jump',5:'aim',6:'math',
              7:'reaction',8:'support',9:'movement'}
MENUS = {1:0,2:1,3:2,4:9,5:10,6:3}

# These seven Lucavi use zero MonsterPortrait in native JOB_DATA despite
# being creature actors. RCC also explicitly lists them as Lucavi. All other
# creature jobs have a nonzero native portrait, including Holy Dragon/Reis,
# Byblos, Automaton, Reaver, Keeper of Darkness and Ultima Demons.
LUCAVI_JOBS = frozenset((60, 62, 64, 65, 67, 69, 73))

# Audited creature actions present only in secondary/master command rows,
# rather than an active job's primary command. They must not fall through to
# the player pool: Blood Drain, Meltdown/Tornado/Quake, the six -ja magicks,
# the first-form Ultima, and Disempower/Dispelja/Return.
CREATURE_SECONDARY_ACTIONS = frozenset((200, 216, 217, 218, 221, 222, 223, 224,
                                      227, 228, 229, 231, 232, 233))
CREATURE_ONLY_MOVEMENTS = frozenset((497, 499, 505))


def creature_jobs(tables):
    """Creature actor IDs from native traits plus the audited Lucavi set."""
    traits = tables.get('_JobTraits', {})
    return {job for job,row in tables['JobData'].items()
            if job and row['JobCommandId'] and any(row[f] for f in JOB_FIELDS)
            and (job in LUCAVI_JOBS or traits.get(job, {}).get('MonsterPortrait', 0))}


def creature_commands(tables):
    """Primary creature command IDs, independent of command table format."""
    return {tables['JobData'][job]['JobCommandId'] for job in creature_jobs(tables)}


def _domain(aid, kind, sources, monster_commands, player_commands, reason):
    if reason:
        return None, 'excluded game entry'
    if aid in CREATURE_ONLY_MOVEMENTS:
        return 'monster', 'creature-only native innate movement'
    if aid in CREATURE_SECONDARY_ACTIONS:
        return 'monster', 'audited creature secondary/master action'
    if kind <= 6 and sources & monster_commands:
        # This is provenance, not an exclusive ownership rule. RCC permits
        # native overlaps and its rare mutations draw from the full catalog.
        if sources & player_commands:
            return 'both', 'native player and creature primary command action'
        return 'monster', 'native creature primary command action'
    if kind >= 7:
        # Shared innates such as Counter and Swiftspell remain player RSMs;
        # this allocator changes learned skillsets, not native innate fields.
        return 'player', 'player reaction/support/movement category'
    if sources:
        return 'player', 'humanoid or native player-menu action'
    return 'player', 'named unreferenced native action'


def attach_catalog(tables,game_dir,project_root):
    from .preview import prepare_inputs
    _,database,inputs = prepare_inputs(game_dir,project_root)
    with closing(sqlite3.connect(database)) as con:
        localized = {r[0]:r[1:] for r in con.execute('SELECT "Key",Name,Description,JpCost1,JpCost2 FROM "Ability-en"')}
        con.row_factory = sqlite3.Row
        overrides = {row['Key']:dict(row) for row in con.execute('SELECT * FROM OverrideAbilityActionData')}
    # Nex rows are overrides, not the native action baseline. A negative
    # scalar or missing array element preserves the corresponding native
    # field; nonnegative values are cast to bytes by the game.
    native = copy.deepcopy(tables.get('_NativeAbilityAttributes',tables['_AbilityAttributes']))
    tables['_NativeAbilityAttributes'] = native
    tables['_AbilityAttributeOverrides'] = overrides
    attributes = copy.deepcopy(native)
    scalar_fields = ('Range','EffectArea','Vertical','Element','Formula','X','Y',
                     'InflictStatus','CT','MPCost')
    for aid,row in attributes.items():
        override = overrides.get(aid,{})
        row['rawFlags12'] = [row['Flags1'],row['Flags2']]
        row['rawFlags34'] = [row['Flags3'],row['Flags4']]
        for pair,fields in (('Flags12',('Flags1','Flags2')),('Flags34',('Flags3','Flags4'))):
            for field,value in zip(fields,json.loads(override.get(pair,'[]'))):
                if value >= 0: row[field] = value & 255
        for field in scalar_fields:
            value = override.get(field,-1)
            if value >= 0: row[field] = value & 255
        row['random_hits'] = bool(row['Flags2'] & 8)
        row['require_sword'] = bool(row['Flags4'] & 8)
        row['require_materia_blade'] = bool(row['Flags4'] & 4)
    tables['_AbilityAttributes'] = attributes
    commands = defaultdict(set)
    for table in ('JobCommandData','MonsterJobCommandData'):
        for command,row in tables[table].items():
            for aid in row.values():
                if aid: commands[aid].add(command)
    jobs = defaultdict(set)
    for job,row in tables['JobData'].items():
        if row['JobCommandId']: jobs[row['JobCommandId']].add(job)
    monster_commands = creature_commands(tables)
    player_commands = {row['JobCommandId'] for job,row in tables['JobData'].items()
                       if job and row['JobCommandId'] and any(row[f] for f in JOB_FIELDS)} - monster_commands
    catalog = {}
    for aid,metadata in tables['_AbilityMetadata'].items():
        name,description,low,high = localized.get(aid,(None,None,0,0))
        kind = metadata['AbilityType']
        reason = ('undefined native type' if not kind else
                  'unused or unnamed game entry' if not name or description == 'UNUSED' else
                  'placeholder game entry' if re.fullmatch(r'A\d+',name) else
                  'marked for deletion by game data' if name.startswith('MARKED FOR DELETION') else None)
        domain,domain_reason = _domain(aid,kind,commands[aid],monster_commands,player_commands,reason)
        catalog[aid] = dict(id=aid,name=name or f'Unnamed {aid}',category=CATEGORIES[kind],native_type=kind,
                            jp_cost=low|(high<<8),flags=metadata['Flags'],ai_flags=metadata['AIBehaviorFlags'],
                            source_commands=sorted(commands[aid]),
                            source_jobs=sorted({j for c in commands[aid] for j in jobs[c]}),
                            source_creature_commands=sorted(commands[aid] & monster_commands),
                            source_player_commands=sorted(commands[aid] & player_commands),
                            domain=domain,domain_reason=domain_reason,
                            eligible=reason is None,excluded_reason=reason,menu=MENUS.get(kind))
    tables['_AbilityCatalog'] = catalog
    tables['_CatalogInputs'] = inputs
    from .rcc_context import prepare_context
    prepare_context(tables,game_dir,project_root)
    return catalog


def pools(tables,domain=None):
    if '_AbilityCatalog' not in tables: raise ValueError('Load the complete ability catalog before randomization')
    if domain not in (None,'player','monster'): raise ValueError('Ability domain must be player or monster')
    return {kind:sorted(a for a,r in tables['_AbilityCatalog'].items()
                       if r['eligible'] and r['native_type']==kind
                       and (domain is None or r['domain'] in (domain,'both')))
            for kind in range(1,10)}


def write_catalog(path,catalog):
    columns = ['id','name','category','native_type','domain','domain_reason','jp_cost','eligible',
               'excluded_reason','source_jobs','source_commands','source_creature_commands',
               'source_player_commands','flags','ai_flags']
    with open(path,'w',newline='',encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file,fieldnames=columns)
        writer.writeheader()
        for row in catalog.values():
            values = {k:row[k] for k in columns}
            for k in ('source_jobs','source_commands','source_creature_commands','source_player_commands'):
                values[k] = ';'.join(map(str,values[k]))
            writer.writerow(values)
