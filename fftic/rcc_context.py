"""Read-only FFTIC inputs for RCC rankings and level-dependent stat boosts.

RCC randomizer.py:3016-3095, 3149-3150, 1889-1909. Encounter records
are inspected here; this module never emits an encounter override.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


VALID_START_STATUSES = 0xCAFCE12A10 | 0x1402100000
LUCAVI = {60, 62, 64, 65, 67, 69, 73, 151}


def prepare_context(tables, game_dir, project_root):
    from .preview import locate_cli, run_cli
    cli = locate_cli(project_root)
    sources = [Path(game_dir)/'data/enhanced'/f'{n:04}.pac' for n in (2, 4)]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    key = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]
    cache = Path(project_root)/'research/rcc-context'/key
    cache.mkdir(parents=True, exist_ok=True)
    receipt, database = cache/'inputs.json', cache/'base.sqlite'
    if receipt.exists():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        for name, digest in record['files_sha256'].items():
            if hashlib.sha256((cache/name).read_bytes()).hexdigest() != digest:
                raise ValueError('RCC context cache changed; re-extract that cache folder')
    else:
        for n in range(1, 5):
            run_cli(cli, ['unpack','-i',sources[0],'-f',f'fftpack/battle_entd{n}_ent.bin','-o',cache,'-g','fft'], cache/f'entry-{n}.log')
        for name in ('overrideentrydata', 'generaljob'):
            run_cli(cli, ['unpack','-i',sources[1],'-f',f'nxd/{name}.nxd','-o',cache,'-g','fft'], cache/f'{name}.log')
        run_cli(cli, ['nxd-to-sqlite','-i',cache/'nxd','-o',database,'-g','fft'], cache/'convert.log')
        files = [database, *sorted((cache/'fftpack').glob('*.bin')), *sorted((cache/'nxd').glob('*.nxd'))]
        record = dict(archive_sha256=hashes, files_sha256={p.relative_to(cache).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
        receipt.write_text(json.dumps(record, indent=2)+'\n')
    units = []
    for n in range(1, 5):
        block = (cache/'fftpack'/f'battle_entd{n}_ent.bin').read_bytes()
        if len(block) != 128*16*40:
            raise ValueError('Unexpected native encounter record size')
        for offset in range(0, len(block), 40):
            row = block[offset:offset+40]
            units.append(dict(map_id=(n-1)*128+offset//640, slot=(offset%640)//40,
                              graphic=row[0], level=row[3], job=row[10], enemy=bool(row[24]&16)))
    # This already independently audited opening record anchors the PS1-like
    # 40-byte layout to FFTIC rather than assuming RCC offsets are portable.
    opening = [u for u in units if u['map_id']==387]
    if opening[0]['job'] != 2 or not {52, 23, 76} <= {u['job'] for u in opening}:
        raise ValueError('Original opening encounter layout changed')
    with closing(sqlite3.connect(database)) as con:
        con.row_factory = sqlite3.Row
        by_key = {(u['map_id'],u['slot']):u for u in units}
        for row in con.execute('SELECT * FROM OverrideEntryData'):
            keys = list(row.keys())
            # Double-keyed NXD keys are the first two SQLite columns.
            unit = by_key.get((row[keys[0]],row[keys[1]]))
            if unit is None: continue
            if row['Disable']: unit['graphic'] = 0; continue
            for column, field in (('Spriteset','graphic'),('MainJob','job'),('Level','level')):
                if row[column] > 0: unit[field] = row[column]&255
        general = {r[0]:dict(r) for r in con.execute('SELECT * FROM GeneralJob')}
    requirements = {}
    def expand(job, visiting=()):
        if job in requirements: return requirements[job]
        if job in visiting: raise ValueError('Original job requirements contain a cycle')
        req = {}
        row = general.get(job)
        if row:
            for source, level in zip(json.loads(row['RequiredJobIds']),json.loads(row['RequiredJobLevels'])):
                if level <= 0: continue
                req[source] = max(req.get(source,0),level)
                for upstream, needed in expand(source,visiting+(job,)).items():
                    req[upstream] = max(req.get(upstream,0),needed)
        requirements[job] = req
        return req
    unlock = {}
    for job in range(20):
        total = 0
        for source, level in expand(job).items():
            costs = json.loads(general[source]['RequiredJobExp'])
            if not 1 <= level <= len(costs): raise ValueError('Invalid original job level requirement')
            total += costs[level-1]
        unlock[job+74] = total
    ranked_generics = sorted(unlock, key=lambda j:(unlock[j],j))
    tables['_RCCGenericRanks'] = {j:i/(len(ranked_generics)-1) for i,j in enumerate(ranked_generics)}
    tables['_RCCUnits'] = [u for u in units if u['graphic']]
    good = sorted({u['job'] for u in tables['_RCCUnits']} & tables['JobData'].keys())
    features = ['HPMultiplier','MPMultiplier','SpeedMultiplier','PAMultiplier','MAMultiplier','Move','CharacterEvasion','MonsterPortrait']
    def value(job, field):
        v = tables['_JobTraits'][job].get(field,tables['JobData'][job].get(field,0))
        return v&15 if field=='Move' else v
    bounds = {}
    for field in features:
        values = [value(j,field) for j in good if value(j,field)>0]
        bounds[field] = (min(values),max(values)) if values else (0,0)
    ranks = {}
    for job in good:
        if sum(value(job,f)==0 for f in features)>len(features)//2:
            ranks[job] = job*0.0000001
            continue
        scores = [(value(job,f)-bounds[f][0])/(bounds[f][1]-bounds[f][0])
                  for f in features if value(job,f) and bounds[f][1]!=bounds[f][0]]
        scores = sorted(scores)[1:]
        rank = sum(scores)/len(scores) if scores else 0
        traits = tables['_JobTraits'][job]
        rank *= 1.5 if job in LUCAVI else 1.3 if not traits['MonsterPortrait'] else 1
        # The loader's aggregate status enum reads these five bytes big-endian;
        # RCC's constants are TableReader little-endian integers.
        statuses = traits.get('InnateStatus',0) | traits.get('StartStatus',0)
        statuses = int.from_bytes(statuses.to_bytes(5, 'big'), 'little')
        if statuses & (0xFFFFFFFFFF^VALID_START_STATUSES): rank /= 10
        ranks[job] = rank
    tables['_RCCRankedJobs'] = sorted(good,key=lambda j:(ranks[j],j))
    tables['_RCCContextInputs'] = record
    return record
