"""RCC terrain and scripted-mover constraints on original FFTIC map meshes."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct

from .preview import locate_cli, run_cli
from .rcc import rng_for


def prepare_maps(game_dir, project_root):
    source = Path(game_dir)/'data/enhanced/0002.pac'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cache = Path(project_root)/'research/rcc-map-inputs'/digest[:16]
    cache.mkdir(parents=True, exist_ok=True)
    receipt = cache/'inputs.json'
    if receipt.exists():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        for name, expected in record['files_sha256'].items():
            if hashlib.sha256((cache/name).read_bytes()).hexdigest() != expected:
                raise ValueError('Original map cache changed: '+name)
        return cache, record
    run_cli(locate_cli(project_root), ['unpack-all','-i',source,'-o',cache,
                                      '-g','fft','--filter','fftpack/map/'], cache/'extract.log')
    paths = sorted((cache/'fftpack/map').glob('*.bin'))
    if not paths:
        raise ValueError('No native map assets extracted')
    record = dict(archive_sha256={source.name:digest}, files_sha256={
        p.relative_to(cache).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    receipt.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return cache, record


def tile(data, upper):
    return dict(terrain_type=data[0]&63, height=data[2], depth=data[3]>>5,
                slope_height=data[3]&31, slope_type=data[4],
                impassable=(data[6]>>1)&1, uncursorable=data[6]&1,
                occupied=0, party=0, upper=upper, unreachable=0)


def bad_regardless(t):
    return int(bool(t['impassable'] or t['uncursorable'] or t['slope_height']>2 or t['depth']>2))


def value(t, attribute):
    if attribute=='bad_regardless':
        return bad_regardless(t)
    if attribute=='bad':
        return int(bool(t['occupied'] or t['unreachable'] or t['terrain_type'] in (0x12,0x24) or bad_regardless(t)))
    return t[attribute]


def read_movements(project_root):
    bundled = Path(__file__).with_name('data')/'rcc-map-movements.txt'
    source = bundled
    if not source.is_file():
        raise ValueError('RCC scripted movement constraints are missing')
    moves = defaultdict(set)
    for line in source.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        map_id, parts = line.split()
        unit,x,y = parts.split(',')
        moves[int(map_id,16)].add((int(unit,16),int(x),int(y)))
    return {k:sorted(v) for k,v in moves.items()}


def read_maps(cache, seed, movements):
    maps = defaultdict(list)
    rng = rng_for(seed,'map-preparation')
    for path in sorted((Path(cache)/'fftpack/map').glob('map_map*_*.bin')):
        if path.stem.endswith('_gns'):
            continue
        data = path.read_bytes()
        if len(data)<108:
            continue
        pointer = struct.unpack_from('<I',data,104)[0]
        if pointer<180 or pointer+4098>len(data):
            continue
        width,length = data[pointer:pointer+2]
        if not (0<width<=64 and 0<length<=64 and width*length<=256):
            continue
        map_id = int(path.name[7:10])
        cells = [tile(data[pointer+2+i*8:pointer+10+i*8],0) for i in range(width*length)]
        for i,t in enumerate(cells):
            offset = pointer+2+(256+i)*8
            up = tile(data[offset:offset+8],1)
            t['upper'] = int(bool(up['height'] and not value(up,'bad')))
        for unit,x,y in movements.get(map_id,[]):
            if 0<=x<width and 0<=y<length:
                cells[y*width+x]['occupied']=1
        remaining = {(x,y) for y in range(length) for x in range(width)
                     if not bad_regardless(cells[y*width+x])}
        zones = []
        while remaining:
            start = min(remaining,key=lambda p:(p[1],p[0]))
            pending, zone = [start],set()
            remaining.remove(start)
            while pending:
                x,y = pending.pop()
                zone.add((x,y))
                for neighbor in ((x,y-1),(x,y+1),(x-1,y),(x+1,y)):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        pending.append(neighbor)
            zones.append(zone)
        if zones:
            maximum = max(map(len,zones))
            largest = rng.choice([z for z in zones if len(z)==maximum])
            for zone in zones:
                if zone != largest:
                    for x,y in zone:
                        cells[y*width+x]['unreachable']=1
        maps[map_id].append(dict(width=width,length=length,cells=cells,
                                source=path.relative_to(cache).as_posix(),terrain_offset=pointer,
                                moves=movements.get(map_id,[])))
    return dict(maps)


def certain_values(variants, attribute):
    width = min(m['width'] for m in variants)
    length = min(m['length'] for m in variants)
    result = []
    for y in range(length):
        row = []
        for x in range(width):
            values = {value(m['cells'][y*m['width']+x],attribute) for m in variants}
            row.append(next(iter(values)) if len(values)==1 else None)
        result.append(row)
    return result


def attach_maps(tables, game_dir, project_root, seed):
    cache,receipt = prepare_maps(game_dir,project_root)
    tables['_RCCMaps'] = read_maps(cache,seed,read_movements(project_root))
    tables['_RCCMapInputs'] = receipt
    return receipt
