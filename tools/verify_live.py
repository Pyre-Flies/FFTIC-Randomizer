"""Read-only verification of a recorded Reloaded-II launch and merged assets.

Requires a launch.json receipt with game_pid, executable, main_module_base,
seed_folder and manifest_sha256. Never starts, stops or writes into a process.
"""
import argparse
from contextlib import closing
import ctypes
from ctypes import wintypes
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fftic.game import ACTION_FIELDS, RSM_FIELDS, JOB_FIELDS, read_game
from fftic.rcc_world_data import JOB_REQUIREMENT_FIELDS, read_native_world
from fftic.preview import locate_cli, run_cli, _table_rows, _normalized_cell


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_process(launch):
    api = ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.ReadProcessMemory.argtypes = [wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,
                                      ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
    api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,
                                              wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.GetProcessTimes.argtypes = [wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    handle = api.OpenProcess(0x10|0x1000,False,launch['game_pid'])
    if not handle:
        raise ValueError('Recorded game process is unavailable')
    name,size = ctypes.create_unicode_buffer(32768),wintypes.DWORD(32768)
    if not api.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)) or Path(name.value).resolve()!=Path(launch['executable']).resolve():
        api.CloseHandle(handle)
        raise ValueError('Recorded process has a different executable')
    times = [wintypes.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(handle,*map(ctypes.byref,times)):
        api.CloseHandle(handle)
        raise ValueError('Cannot verify recorded process creation time')
    created = ((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)/10000000-11644473600
    if abs(created-datetime.fromisoformat(launch['game_start_utc']).timestamp())>.002:
        api.CloseHandle(handle)
        raise ValueError('Recorded PID has been reused')
    base = int(launch['main_module_base'],16)
    def read(rva,size):
        data,got = ctypes.create_string_buffer(size),ctypes.c_size_t()
        if not api.ReadProcessMemory(handle,ctypes.c_void_p(base+rva),data,size,ctypes.byref(got)) or got.value!=size:
            raise ValueError('Incomplete process read at '+hex(rva))
        return data.raw
    return read,lambda:api.CloseHandle(handle)


def xml_value(table,row,field):
    if table=='JobCommandData':
        if field in ACTION_FIELDS:
            slot = ACTION_FIELDS.index(field)
            return row[3+slot]+(256 if row[slot//8]&(1<<(7-slot%8)) else 0)
        slot = RSM_FIELDS.index(field)
        return row[19+slot]+(256 if row[2]&(1<<(7-slot)) else 0)
    if table=='MonsterJobCommandData':
        slot = ACTION_FIELDS.index(field)
        return row[1+slot]+(256 if row[0]&(1<<(7-slot)) else 0)
    if table=='JobData':
        if field in JOB_FIELDS: return row[14+JOB_FIELDS.index(field)]
        if field=='JobCommandId': return row[0]
        if field.startswith('InnateAbilityId'):
            return struct.unpack_from('<H',row,1+(int(field[-1])-1)*2)[0]
        if field in ('EquippableItems','InnateStatus','ImmuneStatus','StartingStatus'):
            start = {'EquippableItems':9,'InnateStatus':27,'ImmuneStatus':32,'StartingStatus':37}[field]
            return int.from_bytes(row[start:start+5],'big')
        return row[42+('AbsorbElements','NullifyElements','HalveElements','WeakElements').index(field)]
    if table=='JobNeedLevelData':
        index = JOB_REQUIREMENT_FIELDS.index(field)
        return (row[index//2]>>(4 if index%2==0 else 0))&15
    if table=='MapTrapFormationData':
        start = (int(field[-1])-1)*6
        name = field[:-1]
        if name in ('X','Y'): return row[start]>>4 if name=='X' else row[start]&15
        if name=='TrapFlags': return row[start+1]
        return struct.unpack_from('<H',row,start+(2 if name=='RareItemId' else 4))[0]
    if table=='ItemOptionsData':
        return row[0] if field=='OptionType' else int.from_bytes(row[1:6],'big')
    if table=='ItemData':
        if field=='Price': return int.from_bytes(row[8:10],'little')
        return row[dict(TypeFlags=3,AdditionalDataId=4,ItemCategory=5,RequiredLevel=2,
                        EquipBonusId=7,ShopAvailability=10)[field]]
    offsets = {
        'CommandTypeData':dict(Menu=0),
        'ItemWeaponData':dict(Range=0,Formula=2,Power=4,Evasion=5,OptionsAbilityId=7),
        'ItemArmorData':dict(HPBonus=0,MPBonus=1),
        'ItemShieldData':dict(PhysicalEvasion=0,MagicalEvasion=1),
        'ItemAccessoryData':dict(PhysicalEvasion=0,MagicalEvasion=1),
        'ItemConsumableData':dict(Formula=0,Z=1,StatusEffectId=2),
        'ItemEquipBonusData':dict(PABonus=0,MABonus=1,SpeedBonus=2,MoveBonus=3,JumpBonus=4),
    }
    return row[offsets[table][field]]


def verify_native(seed,manifest,launch):
    read,close = read_process(launch)
    try:
        payload = (seed/'fftivc.randomizer.seed/runtime-patches.bin').read_bytes()
        if payload[:8]!=b'FFTICRCC' or struct.unpack_from('<I',payload,8)[0]!=1:
            raise ValueError('Unexpected runtime payload')
        count,offset = struct.unpack_from('<I',payload,12)[0],56
        ranges = []
        for _ in range(count):
            rva,size,length = struct.unpack_from('<III',payload,offset)
            offset += 12
            name = payload[offset:offset+length].decode()
            offset += length+size
            wanted = payload[offset:offset+size]
            offset += size
            if read(rva,size)!=wanted:
                raise ValueError('Runtime patch readback differs: '+name)
            ranges.append(dict(name=name,rva=hex(rva),size=size))
        if offset!=len(payload): raise ValueError('Payload parse did not reach end')
        _,build = read_game(Path(launch['executable']).parent)
        locations = build['tables']
        world,_ = read_native_world(launch['executable'])
        checks = {}
        for path in sorted((seed/'fftivc.randomizer.seed/FFTIVC/tables/enhanced').glob('*.xml')):
            table,checked = path.stem,0
            for entry in ET.parse(path).getroot().find('Entries'):
                index = int(entry.findtext('Id'))
                native,adjusted = table,index
                if table=='JobCommandData' and index>=224:
                    native,adjusted = 'JobCommandDataWOTL',index-224
                if table=='MonsterJobCommandData': adjusted -= 176
                spec = locations.get(native) or world[native]
                if not 0<=adjusted<spec['count']: raise ValueError('XML row exceeds native table')
                rva = int(spec['rva'],16) if isinstance(spec['rva'],str) else spec['rva']
                row = read(rva+adjusted*spec['stride'],spec['stride'])
                for element in entry:
                    if element.tag in ('Id','ExtendAbilityIdFlagBits','ExtendReactionSupportMovementIdFlagBits'): continue
                    if xml_value(table,row,element.tag)!=int(element.text):
                        raise ValueError(f'Actual XML table differs: {table}[{index}].{element.tag}')
                    checked += 1
            checks[table] = checked
        return dict(result='passed',native_ranges=ranges,xml_field_checks=checks)
    finally:
        close()


def verify_merged(seed,manifest,launch,audit):
    folder = Path(tempfile.mkdtemp(prefix='merged-',dir=audit))
    required = {}
    tables = manifest['nex_changes']['tables']
    for table in tables:
        locale = table.rsplit('-',1)[1] if '-' in table else None
        pack = 'modded.'+locale+'.pac' if locale else 'modded.pac'
        required.setdefault(pack,[]).append('nxd/'+table.lower().replace('-','.')+'.nxd')
    mod = seed/'fftivc.randomizer.seed'
    assets = [name.removeprefix('FFTIVC/data/enhanced/') for name in manifest['payload_sha256']
              if name.startswith('FFTIVC/data/enhanced/') and not name.endswith('.nxd')]
    required.setdefault('modded.pac',[]).extend(assets)
    packs,cli = {},locate_cli(ROOT)
    for name,entries in sorted(required.items()):
        source = Path(launch['executable']).parent/'data/enhanced'/name
        packs[name] = sha(source)
        for number,entry in enumerate(entries):
            run_cli(cli,['unpack','-i',source,'-f',entry,'-o',folder,'-g','fft'],folder/f'{name}-{number}.log')
            if not (folder/entry).is_file(): raise ValueError('Merged asset is missing: '+entry)
        if packs[name]!=sha(source): raise ValueError('Merged pack changed during verification')
    database = folder/'actual.sqlite'
    run_cli(cli,['nxd-to-sqlite','-i',folder/'nxd','-o',database,'-g','fft'],folder/'convert.log')
    counts = {}
    with closing(sqlite3.connect(database)) as actual, closing(sqlite3.connect(seed/'nex-work/edited.sqlite')) as expected:
        for table in tables:
            got,wanted = _table_rows(actual,table),_table_rows(expected,table)
            if got[:2]!=wanted[:2] or set(got[2])!=set(wanted[2]):
                raise ValueError('Merged Nex schema or key inventory differs: '+table)
            for key,row in got[2].items():
                if list(map(_normalized_cell,row))!=list(map(_normalized_cell,wanted[2][key])):
                    raise ValueError('Merged Nex cell differs: '+str((table,key)))
            counts[table] = len(got[2])
    for name in assets:
        if (folder/name).read_bytes()!=(mod/'FFTIVC/data/enhanced'/name).read_bytes():
            raise ValueError('Merged binary/script asset differs: '+name)
    return dict(result='passed',row_counts=counts,asset_count=len(assets),pack_sha256=packs,
                comparison='Every row and cell of emitted Nex tables and every binary/script asset matched')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,required=True)
    args = parser.parse_args()
    audit = args.audit.resolve()
    if not audit.is_relative_to((ROOT/'research').resolve()): raise ValueError('Audit must stay under project research')
    launch = json.loads((audit/'launch.json').read_text(encoding='utf-8-sig'))
    seed = Path(launch['seed_folder']).resolve()
    if not seed.is_relative_to((ROOT/'outputs').resolve()): raise ValueError('Seed must stay under project outputs')
    if sha(seed/'manifest.json')!=launch['manifest_sha256']: raise ValueError('Seed differs from launch receipt')
    manifest = json.loads((seed/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['payload_sha256'].items():
        path = (seed/'fftivc.randomizer.seed'/name).resolve()
        if not path.is_relative_to((seed/'fftivc.randomizer.seed').resolve()) or sha(path)!=digest:
            raise ValueError('Generated source payload differs from manifest: '+name)
    native = verify_native(seed,manifest,launch)
    merged = verify_merged(seed,manifest,launch,audit)
    result = dict(result='passed',manifest_sha256=launch['manifest_sha256'],game_pid=launch['game_pid'],
                  launch_utc=launch['launch_utc'],native=native,merged=merged)
    (audit/'readback-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f"Verified {len(native['native_ranges'])} runtime ranges, {len(native['xml_field_checks'])} XML tables, "
          f"{len(merged['row_counts'])} Nex tables and {merged['asset_count']} merged assets.")


if __name__=='__main__':
    main()
