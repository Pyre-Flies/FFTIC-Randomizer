"""Global starter costs, using native Nex overrides and localized JP costs."""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import re
from .runtime import resource_root, is_frozen, is_linux, converter_environment



def run_cli(cli, args, log):
    result = subprocess.run([str(cli),*map(str,args)],capture_output=True,text=True,errors='replace',
                            cwd=Path(cli).parent,env=converter_environment(),
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    log.write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode or '[Error]' in result.stdout or '[Error]' in result.stderr:
        raise ValueError(f'FF16Tools conversion failed; see {log}')


def locate_cli(project_root):
    configured = os.environ.get('FFTIC_FF16TOOLS')
    if not is_frozen() and configured and Path(configured).is_file(): return Path(configured).resolve()
    executable = 'FF16Tools.CLI' if is_linux() else 'FF16Tools.CLI.exe'
    choices = sorted((resource_root(project_root)/'vendor').glob('FF16Tools-*/**/'+executable))
    if not choices:
        raise ValueError(f'Nex table output needs {executable}. Install the converter for this platform under vendor/FF16Tools-<version>/ or set FFTIC_FF16TOOLS when running from source.')
    return choices[-1]


def prepare_inputs(game_dir, project_root, include_commands=False):
    cli = locate_cli(project_root)
    packs = sorted((Path(game_dir)/'data/enhanced').glob('0004.*.pac'))
    sources = [Path(game_dir)/'data/enhanced/0004.pac',*packs]
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    material = json.dumps(hashes,sort_keys=True)+('command-labels-v1' if include_commands else '')
    key = hashlib.sha256(material.encode()).hexdigest()[:16]
    cache = Path(project_root)/'research/preview-inputs'/key
    cache.mkdir(parents=True,exist_ok=True)
    database = cache/'base.sqlite'
    receipt = cache/'inputs.json'
    if receipt.exists() and database.exists():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        if record.get('database_sha256') != hashlib.sha256(database.read_bytes()).hexdigest():
            raise ValueError('Preview input cache changed; remove that cache folder and re-extract')
        return cli,database,record
    nxd = cache/'nxd'
    nxd.mkdir(exist_ok=True)
    run_cli(cli,['unpack','-i',sources[0],'-f','nxd/overrideabilityactiondata.nxd','-o',cache,'-g','fft'],cache/'extract-overrides.log')
    for pack in packs:
        locale = pack.name.split('.')[1]
        run_cli(cli,['unpack','-i',pack,'-f',f'nxd/ability.{locale}.nxd','-o',cache,'-g','fft'],cache/f'extract-{locale}.log')
        if include_commands:
            run_cli(cli,['unpack','-i',pack,'-f',f'nxd/jobcommand.{locale}.nxd','-o',cache,'-g','fft'],cache/f'extract-commands-{locale}.log')
    if len(list(nxd.glob('ability.*.nxd'))) != len(packs) or not (nxd/'overrideabilityactiondata.nxd').exists():
        raise ValueError('Preview extraction did not produce every required table')
    if include_commands and len(list(nxd.glob('jobcommand.*.nxd'))) != len(packs):
        raise ValueError('Command-label extraction did not produce every locale')
    run_cli(cli,['nxd-to-sqlite','-i',nxd,'-o',database,'-g','fft'],cache/'convert.log')
    record = dict(archive_sha256=hashes,database_sha256=hashlib.sha256(database.read_bytes()).hexdigest(),
                  nxd_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(nxd.glob('*.nxd'))},
                  cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest())
    receipt.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return cli,database,record


def build_starters(game_dir, project_root, stage, mod, seed,tables):
    from .randomize import starter_actions
    cli,baseline,inputs = prepare_inputs(game_dir,project_root)
    work = Path(stage)/'preview-work'
    work.mkdir()
    edited = work/'edited.sqlite'
    shutil.copyfile(baseline,edited)
    actions = starter_actions(seed,tables)
    with closing(sqlite3.connect(edited)) as con:
        tables = [r[0] for r in con.execute('SELECT name FROM sqlite_master WHERE type="table"') if r[0].startswith('Ability-')]
        for table in tables:
            for aid in actions:
                changed = con.execute(f'UPDATE "{table}" SET JpCost1=0,JpCost2=0 WHERE "Key"=?',(aid,)).rowcount
                if changed != 1: raise ValueError(f'Missing preview action {aid} in {table}')
        for aid in actions:
            if con.execute('UPDATE OverrideAbilityActionData SET CT=0,MPCost=0 WHERE "Key"=?',(aid,)).rowcount != 1:
                raise ValueError(f'Missing preview override {aid}')
        tables.append('OverrideAbilityActionData')
        con.commit()
    target = Path(mod)/'FFTIVC/data/enhanced/nxd'
    target.mkdir(parents=True)
    run_cli(cli,['sqlite-to-nxd','-i',edited,'-t',*tables,'-o',target,'-g','fft'],work/'build.log')
    rebuilt = work/'rebuilt.sqlite'
    run_cli(cli,['nxd-to-sqlite','-i',target,'-o',rebuilt,'-g','fft'],work/'roundtrip.log')
    with closing(sqlite3.connect(edited)) as expected, closing(sqlite3.connect(rebuilt)) as actual, closing(sqlite3.connect(baseline)) as original:
        cell_changes = 0
        for table in tables:
            wanted = expected.execute(f'SELECT * FROM "{table}" ORDER BY "Key"').fetchall()
            got = actual.execute(f'SELECT * FROM "{table}" ORDER BY "Key"').fetchall()
            base = original.execute(f'SELECT * FROM "{table}" ORDER BY "Key"').fetchall()
            if wanted != got: raise ValueError(f'Nex roundtrip changed unexpected data in {table}')
            columns = [r[1] for r in original.execute(f'PRAGMA table_info("{table}")')]
            allowed = {'CT','MPCost'} if table == 'OverrideAbilityActionData' else {'JpCost1','JpCost2'}
            for before,after in zip(base,wanted):
                for col,old,new in zip(columns,before,after):
                    if old != new:
                        if col not in allowed or after[0] not in actions: raise ValueError('Preview modified an unrelated Nex cell')
                        cell_changes += 1
    return dict(actions=list(actions),zero_jp=True,zero_mp=True,instant_cast=True,
                scope='global ability IDs; same selection rule for every enabled human job',localized_tables=tables,changed_cells=cell_changes,
                inputs=inputs,roundtrip='exact rows and cells matched')


def _identifier(name):
    return '"'+name.replace('"','""')+'"'


def _key_columns(con,table):
    columns = [r[1] for r in con.execute('PRAGMA table_info('+_identifier(table)+')')]
    keys = [c for c in columns if re.fullmatch(r'Key(?:[2-9][0-9]*)?',c)]
    keys.sort(key=lambda c:1 if c=='Key' else int(c[3:]))
    if not keys or keys[0]!='Key':
        raise ValueError('Nex table has no supported row key: '+table)
    return columns,keys


def _normalized_cell(value):
    # Nex arrays are JSON encoded in SQLite. Converter whitespace is not an
    # array-data change; every element and all scalar cells must still match.
    if isinstance(value,str) and value.startswith('['):
        try:
            decoded = json.loads(value)
        except (ValueError,TypeError):
            return value
        if isinstance(decoded,list): return decoded
    return value


def _table_rows(con,table):
    columns,keys = _key_columns(con,table)
    rows = con.execute('SELECT * FROM '+_identifier(table)+' ORDER BY '+','.join(map(_identifier,keys))).fetchall()
    key_indices = [columns.index(key) for key in keys]
    keyed = {tuple(row[i] for i in key_indices):row for row in rows}
    if len(keyed)!=len(rows):
        raise ValueError('Duplicate compound Nex row key in '+table)
    return columns,keys,keyed


def _merge_baseline_tables(destination,source,tables):
    """Copy original SQL schema/rows and validate shared converter metadata."""
    source = Path(source)
    if not source.is_file():
        raise ValueError('Required original Nex database is absent: '+str(source))
    with closing(sqlite3.connect(source)) as incoming:
        if incoming.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table','_uniontypes')).fetchone():
            expected = incoming.execute('SELECT * FROM _uniontypes ORDER BY id').fetchall()
            actual = destination.execute('SELECT * FROM _uniontypes ORDER BY id').fetchall()
            if expected!=actual:
                raise ValueError('Nex source databases have incompatible union type metadata')
        for table in tables:
            schema = incoming.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone()
            if not schema:
                raise ValueError('Required original Nex table is absent: '+table)
            exists = destination.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone()
            if exists:
                if _table_rows(destination,table)!=_table_rows(incoming,table):
                    raise ValueError('Conflicting original Nex table baselines: '+table)
                continue
            destination.execute(schema[0])
            rows = incoming.execute('SELECT * FROM '+_identifier(table)).fetchall()
            if rows:
                destination.executemany('INSERT INTO '+_identifier(table)+' VALUES ('+','.join('?' for _ in rows[0])+')',rows)


def _context_database(project_root,before):
    receipt = before.get('_RCCContextInputs') or before.get('_RCCUnitInputs',{}).get('source')
    if not receipt:
        raise ValueError('Unit Nex changes require verified original context inputs')
    key = hashlib.sha256(json.dumps(receipt['archive_sha256'],sort_keys=True).encode()).hexdigest()[:16]
    path = Path(project_root)/'research/rcc-context'/key/'base.sqlite'
    expected = receipt['files_sha256'].get('base.sqlite')
    if not path.is_file() or not expected or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise ValueError('Original unit Nex database differs from its verified receipt')
    return path,receipt


def _world_columns(table):
    if table=='GeneralJob':
        return {'RequiredJobExp','RequiredJobIds','RequiredJobLevels','RequiredJobPositions'}
    if table in {'PoachItem-'+locale for locale in ('en','de','fr','ja','ko','cs','ct')}:
        return {'Unknown2C','Cost','SellPrice','Unknown18'}
    if table in {'CharaName-'+locale for locale in ('en','de','fr','ja','ko','cs','ct')}:
        return {'Name'}
    raise ValueError('Unsupported world Nex table: '+table)


def _apply_sparse_updates(con,table,updates,permitted,allowed):
    columns,keys = _key_columns(con,table)
    for key,fields in updates.items():
        key = tuple(key) if isinstance(key,(tuple,list)) else (key,)
        if len(key)!=len(keys) or any(not isinstance(value,int) for value in key):
            raise ValueError('Invalid compound Nex key for '+table)
        if set(fields)-permitted or set(fields)-set(columns):
            raise ValueError('Unsupported Nex override columns for '+table+': '+str(sorted(set(fields)-permitted)))
        if not fields: continue
        allowed.setdefault(table,{}).setdefault(key,set()).update(fields)
        assignments,values = [],[]
        for field,value in fields.items():
            if isinstance(value,list):
                value = json.dumps(value,separators=(',',':'),allow_nan=False)
            elif not isinstance(value,(int,str)):
                raise ValueError('Nex updates require native integer/text or JSON list values')
            assignments.append(_identifier(field)+'=?')
            values.append(value)
        where = ' AND '.join(_identifier(field)+'=?' for field in keys)
        changed = con.execute('UPDATE '+_identifier(table)+' SET '+','.join(assignments)+' WHERE '+where,values+list(key)).rowcount
        if changed!=1:
            raise ValueError('Missing or ambiguous original Nex row '+table+' '+str(key))


def _apply_battle_inserts(con,updates,before,allowed):
    """Only the two source Warjilis scenarios may add complete Battle rows."""
    columns,keys,base = _table_rows(con,'Battle')
    if columns!=['Key','DLCFlags'] or keys!=['Key']:
        raise ValueError('Verified Battle row schema changed')
    if base.get((10,))!=(10,0):
        raise ValueError('Verified Battle10 insertion template changed')
    scenarios = before.get('_RCCEncounters',{})
    if not scenarios or max(row['scenario'] for row in scenarios.values())!=743:
        raise ValueError('Verified historical-battle scenario inventory changed')
    inserted = {}
    for key,fields in updates.items():
        key = tuple(key) if isinstance(key,(tuple,list)) else (key,)
        if key not in ((744,),(745,)) or key in base:
            raise ValueError('Only new verified Warjilis Battle744/745 rows may be inserted')
        if fields!={'Key':key[0],'DLCFlags':0}:
            raise ValueError('Battle inserts must copy the complete verified Battle10 template')
        con.execute('INSERT INTO Battle(Key,DLCFlags) VALUES(?,?)',(key[0],0))
        allowed.setdefault('Battle',{})[key] = set(columns)
        inserted[key] = dict(fields)
    return inserted


def _apply_conditional_replacements(con,replacements,before,allowed):
    from .rcc_conditionals import validate_replacements,BATTLE_COLUMNS,WORLD_COLUMNS
    validate_replacements(before,replacements)
    for table,groups in replacements.items():
        columns,keys = _key_columns(con,table)
        verified = BATTLE_COLUMNS if table=='EnhancedBattleEvent' else WORLD_COLUMNS
        if tuple(columns)!=verified or keys!=['Key','Key2','Key3']:
            raise ValueError('Verified conditional compound-key schema changed')
        for group,plan in sorted(groups.items()):
            original = con.execute('SELECT * FROM '+_identifier(table)+' WHERE "Key"=? AND Key2=? ORDER BY Key3',group).fetchall()
            actual = [tuple(_normalized_cell(value) for value in row) for row in original]
            expected = [tuple(_normalized_cell(row[field]) for field in columns) for row in plan['expected']]
            if actual!=expected:
                raise ValueError('Conditional baseline guard changed in '+table+' '+str(group))
            con.execute('DELETE FROM '+_identifier(table)+' WHERE "Key"=? AND Key2=?',group)
            for row in plan['rows']:
                key = tuple(row[field] for field in keys)
                if key[:2]!=group or set(row)!=set(columns):
                    raise ValueError('Conditional replacement row differs from its verified group/schema')
                values = [json.dumps(row[field],separators=(',',':')) if isinstance(row[field],list) else row[field] for field in columns]
                con.execute('INSERT INTO '+_identifier(table)+' VALUES('+','.join('?' for _ in columns)+')',values)
                allowed.setdefault(table,{})[key] = set(columns)


def _verify_nex_roundtrip(baseline,edited,rebuilt,selected,allowed,inserts=None,replacements=None):
    """Check complete key inventory, every column and declared changed cells."""
    changed_cells = 0
    with closing(sqlite3.connect(edited)) as wanted, closing(sqlite3.connect(rebuilt)) as actual, closing(sqlite3.connect(baseline)) as original:
        for table in selected:
            columns,keys,expected = _table_rows(wanted,table)
            got_columns,got_keys,got = _table_rows(actual,table)
            base_columns,base_keys,base = _table_rows(original,table)
            if columns!=got_columns or columns!=base_columns or keys!=got_keys or keys!=base_keys:
                raise ValueError('RCC Nex schema changed in '+table)
            inserted = (inserts or {}).get(table,{})
            groups = (replacements or {}).get(table,{})
            replaced_keys = {tuple(row[field] for field in keys) for group in groups.values() for row in group['expected']}
            replacement_rows = {tuple(row[field] for field in keys):row for group in groups.values() for row in group['rows']}
            if expected.keys()!=got.keys() or set(expected)!=(set(base)-replaced_keys)|set(inserted)|set(replacement_rows) or set(base)&set(inserted):
                raise ValueError('RCC Nex compound row inventory changed in '+table)
            for key,row in expected.items():
                if key in inserted and dict(zip(columns,row))!=inserted[key]:
                    raise ValueError('Verified Nex inserted row changed in '+table+' '+str(key))
                if key in replacement_rows and any(_normalized_cell(value)!=_normalized_cell(replacement_rows[key][field]) for field,value in zip(columns,row)):
                    raise ValueError('Verified conditional replacement row changed in '+table+' '+str(key))
                previous = base.get(key,tuple(None for _ in columns))
                for field,new,roundtrip,old in zip(columns,row,got[key],previous):
                    if _normalized_cell(new)!=_normalized_cell(roundtrip):
                        raise ValueError('RCC Nex roundtrip mismatch in '+table+' '+str(key)+' '+field)
                    if _normalized_cell(old)!=_normalized_cell(new):
                        if field not in allowed.get(table,{}).get(key,set()):
                            raise ValueError('Unrelated Nex cell changed in '+table+' '+str(key)+' '+field)
                        changed_cells += 1
    return changed_cells


def build_rcc_nex(game_dir, project_root, stage, mod, before, after, seed, free=False,ability_mode='rcc'):
    """Emit all authorized RCC Nex changes and verify complete keyed tables."""
    from .randomize import starter_actions
    jp = dict(after.get('_RCCStatAudit',{}).get('jp_cost_updates',{}))
    # Metadata is the final native state after innates, JP, monsters and events.
    jp.update({a:r['JPCost'] for a,r in after.get('_RCCMetadataUpdates',{}).items() if 'JPCost' in r})
    action = {a:dict(fields) for a,fields in after.get('_RCCActionAudit',{}).get('action_updates',{}).items()}
    for aid,fields in after.get('_RCCStatusAudit',{}).get('action_updates',{}).items():
        action.setdefault(aid,{}).update(fields)
    world = after.get('_RCCWorldNexUpdates',{})
    entries = after.get('_RCCEntryNexUpdates',{})
    requested_inserts = after.get('_RCCWorldNexInserts',{})
    conditional_replacements = after.get('_RCCConditionalReplacements',{})
    if set(requested_inserts)-{'Battle'}:
        raise ValueError('Only verified Battle scenario rows may be inserted')
    starters = starter_actions(seed,before) if free else ()
    for aid in starters:
        jp[aid] = 0
        action.setdefault(aid,{}).update(CT=0,MPCost=0)
    owners = after['_RCCAbilityAudit'].get('selected_owners',[]) if ability_mode=='full' else []
    command_owners = [owner for owner in owners if owner['table']=='JobCommandData']
    if not jp and not action and not command_owners and not world and not entries and not requested_inserts and not conditional_replacements: return None
    cli,baseline,inputs = prepare_inputs(game_dir,project_root,include_commands=bool(command_owners))
    work = Path(stage)/'nex-work'
    work.mkdir()
    merged_sources = []
    if world or entries or requested_inserts or conditional_replacements:
        combined = work/'combined-baseline.sqlite'
        shutil.copyfile(baseline,combined)
        with closing(sqlite3.connect(combined)) as con:
            needed = set(world)|set(requested_inserts)|set(conditional_replacements)
            supplied = set()
            for record in before.get('_RCCAdditionalNexSources',[]):
                selected_source_tables = sorted(needed & set(record.get('tables',[])))
                if not selected_source_tables: continue
                database = Path(record.get('database',''))
                expected = record.get('files_sha256',{}).get(database.name)
                if not database.is_file() or not expected or hashlib.sha256(database.read_bytes()).hexdigest()!=expected:
                    raise ValueError('Additional original Nex database differs from its verified receipt')
                _merge_baseline_tables(con,database,selected_source_tables)
                supplied.update(selected_source_tables)
                merged_sources.append(dict(kind='additional original tables',tables=selected_source_tables,database_sha256=expected))
            if world or requested_inserts or conditional_replacements:
                for table in world: _world_columns(table)
                remaining = sorted(needed-supplied)
                if remaining:
                    record = before.get('_RCCWorldInputs',{})
                    database = Path(record.get('database',''))
                    expected = record.get('files_sha256',{}).get(database.name)
                    if not database.is_file() or not expected or hashlib.sha256(database.read_bytes()).hexdigest()!=expected:
                        raise ValueError('Original world Nex database differs from its verified receipt')
                    _merge_baseline_tables(con,database,remaining)
                    merged_sources.append(dict(kind='world',database_sha256=expected))
            if entries:
                database,record = _context_database(project_root,before)
                _merge_baseline_tables(con,database,['OverrideEntryData'])
                merged_sources.append(dict(kind='unit context',database_sha256=record['files_sha256']['base.sqlite']))
            con.commit()
        baseline = combined
    edited = work/'edited.sqlite'
    shutil.copyfile(baseline,edited)
    allowed = {}
    labels = {}
    inserts = {}
    with closing(sqlite3.connect(edited)) as con:
        locales = [r[0] for r in con.execute('SELECT name FROM sqlite_master WHERE type="table"') if r[0].startswith('Ability-')]
        selected = []
        if jp:
            for table in locales:
                selected.append(table)
                allowed[table] = {}
                for aid,cost in jp.items():
                    if not 0<=cost<=65535: raise ValueError('JP cost outside native range')
                    if con.execute(f'UPDATE "{table}" SET JpCost1=?,JpCost2=? WHERE "Key"=?',(cost&255,cost>>8,aid)).rowcount != 1:
                        raise ValueError(f'Missing ability {aid} in {table}')
                    allowed[table][(aid,)] = {'JpCost1','JpCost2'}
        if action:
            table = 'OverrideAbilityActionData'
            selected.append(table)
            allowed[table] = {}
            permitted = {'Range','EffectArea','Vertical','Element','Formula','X','Y','InflictStatus','CT','MPCost','Flags12','Flags34'}
            for aid,fields in action.items():
                if set(fields)-permitted: raise ValueError('Unsupported action override field')
                allowed[table][(aid,)] = set(fields)
                for field,value in fields.items():
                    stored = json.dumps(value,separators=(',',':')) if isinstance(value,list) else value
                    if con.execute(f'UPDATE "{table}" SET "{field}"=? WHERE "Key"=?',(stored,aid)).rowcount != 1:
                        raise ValueError(f'Missing action override {aid}')
        if command_owners:
            # Command names must describe the new profile. Leaving Archer's
            # old "Aim" title would conceal its replacement in Full mode.
            generic = {
                'en':('Randomized Actions','Actions assigned to this job by the randomizer.'),
                'de':('Zufällige Fertigkeiten','Durch den Randomizer zugewiesene Fertigkeiten.'),
                'fr':('Actions aléatoires','Actions attribuées à ce métier par le randomiseur.'),
                'ja':('ランダムアビリティ','ランダマイザーで割り当てられたアビリティ。'),
                'ko':('무작위 행동','랜덤화 도구가 이 직업에 배정한 행동.'),
                'cs':('随机技能','随机器分配给此职业的技能。'),
                'ct':('隨機技能','隨機工具分配給此職業的技能。'),
            }
            source_commands = {1:6,2:20,3:21,4:17,7:19,9:18,10:8}
            command_tables = [r[0] for r in con.execute('SELECT name FROM sqlite_master WHERE type="table"') if r[0].startswith('JobCommand-')]
            for table in command_tables:
                locale = table.split('-')[1]
                selected.append(table)
                allowed[table] = {}
                labels[table] = {}
                # Snapshot the original labels before updating any owners.
                original = {r[0]:r[1:] for r in con.execute(f'SELECT "Key",Name,Description,Description2 FROM "{table}"')}
                for owner in command_owners:
                    command,menu = owner['id'],owner['menu']
                    source = original.get(source_commands.get(menu),())
                    if source and source[0]:
                        values = source
                    else:
                        name,description = generic[locale]
                        values = (name,description,description)
                    if con.execute(f'UPDATE "{table}" SET Name=?,Description=?,Description2=? WHERE "Key"=?',(*values,command)).rowcount != 1:
                        raise ValueError(f'Missing command label {command} in {table}')
                    allowed[table][(command,)] = {'Name','Description','Description2'}
                    labels[table][command] = dict(zip(('Name','Description','Description2'),values))
        for table,updates in sorted(world.items()):
            selected.append(table)
            _apply_sparse_updates(con,table,updates,_world_columns(table),allowed)
        if entries:
            from .rcc_encounter_data import NEX_FIELDS
            selected.append('OverrideEntryData')
            _apply_sparse_updates(con,'OverrideEntryData',entries,set(NEX_FIELDS)|{'HigherElevation','Disable'},allowed)
        if requested_inserts:
            selected.append('Battle')
            inserts['Battle'] = _apply_battle_inserts(con,requested_inserts['Battle'],before,allowed)
        if conditional_replacements:
            selected.extend(sorted(conditional_replacements))
            _apply_conditional_replacements(con,conditional_replacements,before,allowed)
        con.commit()
    target = Path(mod)/'FFTIVC/data/enhanced/nxd'
    target.mkdir(parents=True)
    run_cli(cli,['sqlite-to-nxd','-i',edited,'-t',*selected,'-o',target,'-g','fft'],work/'build.log')
    rebuilt = work/'rebuilt.sqlite'
    run_cli(cli,['nxd-to-sqlite','-i',target,'-o',rebuilt,'-g','fft'],work/'roundtrip.log')
    changed_cells = _verify_nex_roundtrip(baseline,edited,rebuilt,selected,allowed,inserts,conditional_replacements)
    return dict(jp_cost_updates=jp,action_updates=action,command_labels=labels,testing_actions=list(starters),
                world_updates=[dict(table=table,key=list(key),fields=fields) for table,updates in sorted(world.items()) for key,fields in sorted(updates.items())],
                entry_updates=[dict(key=list(key),fields=fields) for key,fields in sorted(entries.items())],
                inserted_rows=[dict(table=table,key=list(key),fields=fields) for table,rows in sorted(inserts.items()) for key,fields in sorted(rows.items())],
                conditional_groups=[dict(table=table,key=list(key),before_rows=len(plan['expected']),after_rows=len(plan['rows'])) for table,groups in sorted(conditional_replacements.items()) for key,plan in sorted(groups.items())],
                tables=selected,changed_cells=changed_cells,inputs=inputs,merged_sources=merged_sources,
                roundtrip='exact rows and cells matched')
