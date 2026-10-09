"""RCC z community names, consumed by length as in get_new_names.

Only the three256-name native random-name pools (keys256..1023) change.
Named recruits can also have IsGeneric=1, so that flag alone is insufficient.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from .rcc import rng_for,randint,remember_rng


NAMES_FILE = Path(__file__).with_name('data')/'rcc-generic-names.txt'


def prepare_names(tables,game_dir,project_root):
    from .preview import locate_cli,run_cli
    cli = locate_cli(project_root)
    packs = sorted((Path(game_dir)/'data/enhanced').glob('0004.*.pac'))
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in packs}
    key = hashlib.sha256((json.dumps(hashes,sort_keys=True)+'names-z-v1').encode()).hexdigest()[:16]
    cache = Path(project_root)/'research/rcc-names'/key
    database,receipt = cache/'base.sqlite',cache/'inputs.json'
    cache.mkdir(parents=True,exist_ok=True)
    if receipt.exists():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        for name,digest in record['files_sha256'].items():
            if hashlib.sha256((cache/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('Generic-name cache changed; re-extract the affected cache')
        record['database'] = str(database.resolve())
    else:
        for pack in packs:
            locale = pack.name.split('.')[1]
            run_cli(cli,['unpack','-i',pack,'-f',f'nxd/charaname.{locale}.nxd','-o',cache,'-g','fft'],cache/f'{locale}.log')
        run_cli(cli,['nxd-to-sqlite','-i',cache/'nxd','-o',database,'-g','fft'],cache/'convert.log')
        files = [database,*sorted((cache/'nxd').glob('*.nxd'))]
        record = dict(database=str(database.resolve()),archive_sha256=hashes,
                      files_sha256={p.relative_to(cache).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
        receipt.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    with closing(sqlite3.connect(database)) as con:
        con.row_factory = sqlite3.Row
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'CharaName-%'")]
        rows = {name:{r['Key']:dict(r) for r in con.execute('SELECT * FROM "'+name+'"')} for name in names}
    if len(rows)!=7 or any(not all(key in r and r[key]['IsGeneric'] and r[key]['Name'] for key in range(256,1024)) for r in rows.values()):
        raise ValueError('The three256-name Enhanced random-name pools changed')
    tables['_RCCNameTables'] = rows
    tables.setdefault('_RCCAdditionalNexSources',[]).append(dict(record,tables=names))
    return record


def consume_names(basenames,rng):
    """Literal RCC4831-4883 string logic, with its depleted length buckets."""
    candidates = {len(name):[] for name in basenames}
    def remove_char(line):
        removable = [i for i,char in enumerate(line) if i>0 and char.lower() in 'aeiou']
        if len(line)-1 not in removable:
            removable.append(len(line)-1)
        i = rng.choice(removable)
        return line[:i]+line[i+1:]
    for line in NAMES_FILE.read_text(encoding='utf-8').splitlines():
        line = line.replace('_',' ').strip()
        if len(line) not in candidates and ' ' in line:
            line = line.replace(' ','')
        if len(line) not in candidates:
            while len(line) not in candidates:
                line = remove_char(line)
                if not line:
                    break
            if len(line)-1 in candidates and rng.choice((True,False)):
                line = remove_char(line)
        line = line.strip()
        if len(line) in candidates:
            candidates[len(line)].append(line)
    transitions = {}
    shuffled = list(basenames)
    rng.shuffle(shuffled)
    for name in shuffled:
        choices = list(candidates[len(name)])
        if not choices:
            raise ValueError('RCC random-name bucket exhausted for length '+str(len(name)))
        choices = choices[:randint(rng,1,len(choices))]
        selected = rng.choice(choices)
        candidates[len(name)].remove(selected)
        transitions[name] = ' '.join(word[0].upper()+word[1:] if word==word.lower() else word for word in selected.split())
    return [transitions[name] for name in basenames]


def apply_names(before,result,seed,flags,*,environment=None):
    if 'z' not in flags:
        return dict(changed_names=0)
    from .rcc_world_data import world_nex_update
    original = before['_RCCNameTables']['CharaName-en']
    basenames = [original[key]['Name'] for key in range(256,1024)]
    env = environment or result.get('_RCCSpecialEnvironment')
    rng = env['random'] if env else rng_for(seed,'specials-z')
    names = consume_names(basenames,rng)
    for table in result['_RCCNameTables']:
        for key,name in zip(range(256,1024),names):
            world_nex_update(result,table,(key,),dict(Name=name))
    remember_rng(result,rng)
    return dict(source='RCC4831-4916',changed_names=768,localized_tables=7,
                randomized_keys=[256,1023],preserved_named_recruits=[117,118,120,121,127],
                pool_policy='same-length community names consumed; repeated original names share replacement')
