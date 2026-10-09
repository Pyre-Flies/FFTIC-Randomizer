"""Encode native patches; the runtime verifies exact EXE hash and all old bytes."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

from .game import ENHANCED_SHA256
from .runtime import resource_root,is_frozen


def metadata_patches(game_dir,before,after,build):
    """Patch only verified JP/learn/AI fields, preserving type and flags.

    The upstream AbilityData serializer's type setter mixes its nibble with
    ability flags. Emit no AbilityData XML; preserve that byte directly.
    """
    location = build['tables']['AbilityMetadata']
    raw,rva = int(location['file_offset'],16),int(location['rva'],16)
    exe = (Path(game_dir)/'FFT_enhanced.exe').read_bytes()
    size = location['stride']*location['count']
    original = exe[raw:raw+size]
    changed = bytearray(original)
    offsets = {'JPCost':(0,2),'LearnChance':(2,1),'AIBehaviorFlags':(4,4)}
    for aid,fields in after.get('_RCCMetadataUpdates',{}).items():
        if set(fields)-offsets.keys():
            raise ValueError('Unverified ability metadata mutation')
        for field,value in fields.items():
            offset,width = offsets[field]
            start = aid*8+offset
            changed[start:start+width] = value.to_bytes(width,'little')
    if original==changed:
        return []
    if any(changed[n]!=original[n] for n in range(3,size,8)):
        raise ValueError('Ability metadata type/flag byte was changed')
    return [dict(name='Ability metadata (JP, learning, AI)',rva=rva,expected=original,data=bytes(changed))]


def write_runtime(game_dir,project_root,mod,patches):
    if not patches:
        return None
    project_root,mod = Path(project_root),Path(mod)
    data = (Path(game_dir)/'FFT_enhanced.exe').read_bytes()
    if hashlib.sha256(data).hexdigest()!=ENHANCED_SHA256:
        raise ValueError('Native patches require the verified Enhanced executable')
    pe = struct.unpack_from('<I',data,60)[0]
    timestamp = struct.unpack_from('<I',data,pe+8)[0]
    image_size = struct.unpack_from('<I',data,pe+24+56)[0]
    records, intervals, audit = [],[],[]
    for patch in sorted(patches,key=lambda p:p['rva']):
        old,new,rva = bytes(patch['expected']),bytes(patch['data']),patch['rva']
        if old==new:
            continue
        if not old or len(old)!=len(new) or len(old)>4*1024*1024 or not 0<=rva<rva+len(old)<=image_size:
            raise ValueError('Invalid native patch range')
        if any(rva<end and start<rva+len(old) for start,end in intervals):
            raise ValueError('Native patch ranges overlap')
        label = patch['name'].removeprefix('RCC ')
        name = label.encode('utf-8')
        if len(name)>256:
            raise ValueError('Native patch label too long')
        intervals.append((rva,rva+len(old)))
        records.append(struct.pack('<III',rva,len(old),len(name))+name+old+new)
        audit.append(dict(name=label,rva=f'0x{rva:X}',size=len(old),
                          changed_bytes=sum(a!=b for a,b in zip(old,new)),
                          original_sha256=hashlib.sha256(old).hexdigest(),
                          generated_sha256=hashlib.sha256(new).hexdigest()))
    if not records:
        return None
    resources = resource_root(project_root)
    source = resources/'native/RuntimePatches.cpp'
    key = hashlib.sha256(source.read_bytes()+(resources/'tools/build_native.ps1').read_bytes()).hexdigest()
    bundled = resources/'native/runtime'
    receipt = bundled/'build.json'
    dll = bundled/'fftic-rcc-runtime.dll'
    verified_bundle = False
    if receipt.is_file() and dll.is_file():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        verified_bundle = (record.get('source_sha256')==key and
                           record.get('dll_sha256')==hashlib.sha256(dll.read_bytes()).hexdigest())
    build = project_root/'research/native-build'
    stamp = build/'source.sha256'
    if not verified_bundle:
        if is_frozen():
            raise ValueError('Bundled runtime integrity check failed. Re-extract the randomizer package.')
        dll = build/'fftic-rcc-runtime.dll'
        if not dll.exists() or not stamp.exists() or stamp.read_text().strip()!=key:
            result = subprocess.run(['pwsh','-NoProfile','-File',str(project_root/'tools/build_native.ps1')],
                                    capture_output=True,text=True,errors='replace')
            (project_root/'research/native-build.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
            if result.returncode or not dll.is_file():
                raise ValueError('Native runtime compilation failed; see research/native-build.log')
            stamp.write_text(key+'\n',encoding='ascii')
    shutil.copyfile(dll,mod/dll.name)
    # Reloaded's native Init runs before the synchronous final scan barrier.
    # A dependent managed mod loads this DLL only from OnModLoaderInitialized,
    # after scanner callbacks and Nenkai's table/pack application have finished.
    bridge_source = resources/'native/startup/RuntimeBridge.cs'
    bridge_key = hashlib.sha256(bridge_source.read_bytes()+
                               (resources/'tools/build_startup.ps1').read_bytes()).hexdigest()
    bridge = bundled/'fftic-rcc-startup.dll'
    verified_bridge = False
    if receipt.is_file() and bridge.is_file():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        verified_bridge = (record.get('bridge_source_sha256')==bridge_key and
                           record.get('bridge_dll_sha256')==hashlib.sha256(bridge.read_bytes()).hexdigest())
    if not verified_bridge:
        if is_frozen():
            raise ValueError('Bundled startup integrity check failed. Re-extract the randomizer package.')
        bridge_build = project_root/'research/startup-build'
        bridge = bridge_build/'fftic-rcc-startup.dll'
        bridge_stamp = bridge_build/'source.sha256'
        if not bridge.is_file() or not bridge_stamp.is_file() or bridge_stamp.read_text().strip()!=bridge_key:
            result = subprocess.run(['pwsh','-NoProfile','-File',str(project_root/'tools/build_startup.ps1')],
                                    capture_output=True,text=True,errors='replace')
            (project_root/'research/startup-build.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
            if result.returncode or not bridge.is_file():
                raise ValueError('Managed startup compilation failed; see research/startup-build.log')
            bridge_stamp.write_text(bridge_key+'\n',encoding='ascii')
    shutil.copyfile(bridge,mod/bridge.name)
    payload = b'FFTICRCC'+struct.pack('<II',1,len(records))+bytes.fromhex(ENHANCED_SHA256)+struct.pack('<II',timestamp,image_size)+b''.join(records)
    (mod/'runtime-patches.bin').write_bytes(payload)
    return dict(dll=dll.name,guard='exact executable SHA-256 and every original patch byte; transaction preflight',
                patches=audit,payload_sha256=hashlib.sha256(payload).hexdigest(),source_sha256=key,
                dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(),bundled_runtime=verified_bundle,
                bridge=bridge.name,bridge_source_sha256=bridge_key,
                bridge_dll_sha256=hashlib.sha256(bridge.read_bytes()).hexdigest(),bundled_bridge=verified_bridge)
