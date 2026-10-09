"""Package generator sources only; never include local vanilla/cache inputs."""
import hashlib
import json
import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from fftic import VERSION

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seed-folder',required=True,type=Path,action='append',help='Generated seed folder to checksum; repeat for both modes')
args = parser.parse_args()
seed_folders = list(dict.fromkeys(p.resolve() for p in args.seed_folder))
for seed_folder in seed_folders:
    if ROOT/'outputs' not in seed_folder.parents:
        raise ValueError('Seed folder must be inside this project outputs directory')
    manifest = json.loads((seed_folder/'manifest.json').read_text(encoding='utf-8-sig'))
    if manifest['generator_version'] != VERSION:
        raise ValueError('Seed version differs from source version')

files = [ROOT/name for name in ('randomizer.py','Launch Randomizer.cmd','README.md','AGENTS.md','THIRD_PARTY_NOTICES.txt','LICENSE','.gitignore')]
for directory in ('fftic','docs','tests','tools','native'):
    files += [p for p in (ROOT/directory).rglob('*') if p.is_file()
              and '__pycache__' not in p.parts and p.suffix in ('.py','.ps1','.md','.txt','.cpp','.h','.json','.cs','.csproj')]
runtime = ROOT/'native/runtime/fftic-rcc-runtime.dll'
receipt = json.loads((runtime.parent/'build.json').read_text(encoding='utf-8'))
source_key = hashlib.sha256((ROOT/'native/RuntimePatches.cpp').read_bytes()+
                            (ROOT/'tools/build_native.ps1').read_bytes()).hexdigest()
if receipt['source_sha256']!=source_key or receipt['dll_sha256']!=hashlib.sha256(runtime.read_bytes()).hexdigest():
    raise ValueError('Bundled native runtime differs from its source/build receipt')
files.append(runtime)
bridge = runtime.parent/'fftic-rcc-startup.dll'
bridge_key = hashlib.sha256((ROOT/'native/startup/RuntimeBridge.cs').read_bytes()+
                            (ROOT/'tools/build_startup.ps1').read_bytes()).hexdigest()
if receipt['bridge_source_sha256']!=bridge_key or receipt['bridge_dll_sha256']!=hashlib.sha256(bridge.read_bytes()).hexdigest():
    raise ValueError('Bundled startup bridge differs from its source/build receipt')
files.append(bridge)
target = ROOT/'outputs'/f'fftic-randomizer-{VERSION}-source.zip'
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(files):
        info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(),date_time=(2026,1,1,0,0,0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info,path.read_bytes())
with zipfile.ZipFile(target) as archive:
    if archive.testzip(): raise ValueError('Source package failed integrity check')
    if any(name.startswith(('research/','vendor/','outputs/')) for name in archive.namelist()):
        raise ValueError('Private input found in source package')
seeds = [folder/'randomizer-mod.zip' for folder in seed_folders]
checksums = {p.relative_to(ROOT/'outputs').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [target,*seeds]}
(ROOT/'outputs'/f'fftic-randomizer-{VERSION}-checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
print(f'Packaged {len(files)} source files: {target}')
