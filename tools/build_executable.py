"""Build the portable Windows GUI, including Python/Tk and the table converter.

Build dependencies are isolated in research/build-env. Downloaded converter,
.NET runtime and license inputs remain under vendor, never game data. Only
explicit authored-resource roots are accepted into the application bundle.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import urllib.request
import urllib.error
import venv
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fftic import VERSION

PYINSTALLER_VERSION = '6.22.3'
FF16_VERSION = '1.13.3'
FF16_COMMIT = '14361aefa1e1265096b42cad95cd9f01550a0457'
FF16_CLI_SHA256 = 'd999fd169898a24297abaaa383f01b20cf13a8bf313bfd5a724da5382bcf913b'
FF16_ZIP_SHA256 = '9d653d95e2da9770fbbf12431bbcface876d209d1824925a08941aa87eee05e3'
DOTNET_VERSION = '9.0.20'
DOTNET_URL = ('https://builds.dotnet.microsoft.com/dotnet/Runtime/'
              f'{DOTNET_VERSION}/dotnet-runtime-{DOTNET_VERSION}-win-x64.zip')
DOTNET_SHA512 = ('6f7241fab7a8003813c3c8a59005e368fe53525e3cf08ab1cc052103f2f422af6'
                 'bd1b20b838c283283a8a709d52a6aea2379686fe6cb07cc0fa7119f2ef2b2bf')
BUNDLE_SIGNATURE = bytes.fromhex('8b1202b96a612038727b930214d7a03213f5b9e6efae3318ee3b2dce24b36aae')
BUILD = ROOT / 'research/executable-build'
LICENSES = BUILD / 'license-notices'


def digest(path: Path, algorithm: str = 'sha256') -> str:
    return hashlib.new(algorithm, path.read_bytes()).hexdigest()


def download(url: str, destination: Path, expected: str | None = None,
             algorithm: str = 'sha256') -> Path:
    if destination.is_file() and (expected is None or digest(destination, algorithm) == expected):
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'FFTIC-Randomizer-build'})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            content = response.read()
    except urllib.error.URLError as error:
        raise ValueError(f'Could not download {url}: {error}') from error
    if expected is not None and hashlib.new(algorithm, content).hexdigest() != expected:
        raise ValueError(f'Download hash mismatch: {url}')
    destination.write_bytes(content)
    return destination


def extract_archive(archive: Path, target: Path) -> None:
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            resolved = (target / entry.filename).resolve()
            if target not in resolved.parents and resolved != target:
                raise ValueError(f'Unsafe archive path: {entry.filename}')
        bundle.extractall(target)


def verify_archive_contents(archive: Path, target: Path, expected: str,
                            algorithm: str = 'sha256', prefix: str = '') -> None:
    if not archive.is_file() or digest(archive, algorithm) != expected:
        raise ValueError(f'Verified dependency archive missing: {archive.name}')
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            if entry.is_dir() or not entry.filename.startswith(prefix):
                continue
            relative = entry.filename[len(prefix):]
            if relative.lower().endswith('.pdb'):
                continue
            path = target / relative
            if not path.is_file() or path.read_bytes() != bundle.read(entry):
                raise ValueError(f'Extracted dependency differs from verified archive: {relative}')


def converter_dependencies(cli: Path) -> dict:
    """Read the standard .NET single-file header without executing the CLI."""
    binary = cli.read_bytes()
    position = binary.find(BUNDLE_SIGNATURE)
    if position < 8:
        raise ValueError('Converter is not the expected .NET single-file application')
    header = struct.unpack_from('<Q', binary, position - 8)[0]
    major, minor, count = struct.unpack_from('<III', binary, header)
    if (major, minor) != (6, 0) or count < 1:
        raise ValueError('Unsupported converter bundle header')
    cursor = header + 12
    length, shift = 0, 0
    while True:
        byte = binary[cursor]
        cursor += 1
        length |= (byte & 127) << shift
        if not byte & 128:
            break
        shift += 7
    cursor += length  # bundle ID
    deps_offset, deps_size, runtime_offset, runtime_size = struct.unpack_from('<QQQQ', binary, cursor)
    deps = json.loads(binary[deps_offset:deps_offset + deps_size])
    runtime = json.loads(binary[runtime_offset:runtime_offset + runtime_size])
    if runtime['runtimeOptions']['framework']['name'] != 'Microsoft.NETCore.App':
        raise ValueError('Converter runtime requirements changed')
    return dict(packages={name: data for name, data in deps['libraries'].items()
                          if data.get('type') == 'package'}, runtime=runtime)


def nuget_notices(package: tuple[str, dict]) -> dict:
    identity, dependency = package
    name, version = identity.rsplit('/', 1)
    package_url = f'https://api.nuget.org/v3-flatcontainer/{name.lower()}/{version.lower()}/{name.lower()}.{version.lower()}.nupkg'
    archive = download(package_url, ROOT / 'vendor/executable-licenses/nuget' / f'{name}.{version}.nupkg')
    target = LICENSES / 'converter-dependencies' / f'{name}-{version}'
    target.mkdir(parents=True, exist_ok=True)
    selected = []
    with zipfile.ZipFile(archive) as bundle:
        nuspec_path = next(path for path in bundle.namelist() if path.endswith('.nuspec'))
        metadata = ET.fromstring(bundle.read(nuspec_path))
        license_node = next((node for node in metadata.iter() if node.tag.rsplit('}', 1)[-1] == 'license'), None)
        license_url = next((node.text for node in metadata.iter() if node.tag.rsplit('}', 1)[-1] == 'licenseUrl'), None)
        for path in bundle.namelist():
            basename = Path(path).name.lower()
            explicit = license_node is not None and license_node.attrib.get('type') == 'file' and path == license_node.text
            if explicit or any(token in basename for token in ('license', 'copying', 'notice', 'copyright')):
                if path.endswith('/'):
                    continue
                destination = target / path.replace('/', '__')
                destination.write_bytes(bundle.read(path))
                selected.append(destination.name)
        (target / 'package.nuspec').write_bytes(bundle.read(nuspec_path))
    expression = license_node.text if license_node is not None else None
    if expression and license_node.attrib.get('type') == 'expression':
        # NuGet package license expressions are exact SPDX identifiers. Retain
        # upstream package metadata/copyright plus the full official SPDX text.
        chosen = 'MIT' if expression == 'MIT OR Unlicense' else expression
        if chosen not in {'MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'Zlib'}:
            raise ValueError(f'License text required for {identity}: {expression}')
        destination = download(f'https://raw.githubusercontent.com/spdx/license-list-data/main/text/{chosen}.txt',
                               target / f'{chosen}.txt')
        selected.append(destination.name)
    if not selected and license_url and license_url.startswith('https://') and 'aka.ms/deprecateLicenseUrl' not in license_url:
        if license_url == 'https://github.com/HelloKitty/Iconic.Zlib.Netstandard':
            license_url = 'https://raw.githubusercontent.com/HelloKitty/Iconic.Zlib.Netstandard/master/LICENSE'
        destination = download(license_url, target / 'LICENSE-from-package-url.txt')
        if b'<!doctype html' in destination.read_bytes()[:200].lower():
            raise ValueError(f'License URL returned HTML instead of terms: {identity}')
        selected.append(destination.name)
    if not selected:
        raise ValueError(f'No redistribution notice located for {identity}: {expression or license_url}')
    return dict(package=identity, package_url=package_url, package_sha256=digest(archive),
                license=expression, license_url=license_url, notices=selected,
                dependency_sha512=dependency.get('sha512'))


def prepare_dependencies(cli: Path, dotnet: Path) -> None:
    converter_archive = download(
        f'https://github.com/Nenkai/FF16Tools/releases/download/{FF16_VERSION}/FF16Tools.CLI-{FF16_VERSION}-win-x64.zip',
        ROOT / 'vendor' / f'FF16Tools.CLI-{FF16_VERSION}-win-x64.zip', FF16_ZIP_SHA256)
    if not cli.is_file():
        extract_archive(converter_archive, cli.parent.parent)
    archive = download(DOTNET_URL, ROOT / 'vendor' / f'dotnet-runtime-{DOTNET_VERSION}-win-x64.zip', DOTNET_SHA512, 'sha512')
    extract_archive(archive, dotnet)
    LICENSES.mkdir(parents=True, exist_ok=True)
    for repository, revision, destination in (
            ('FF16Tools', FF16_COMMIT, 'FF16Tools-LICENSE.txt'),
            ('fftivc-nex-layouts', 'd4a60952531d82bfd8a4fbb76b1f9b363f721dc1', 'FFTIC-Nex-layouts-LICENSE.txt'),
            ('ffxvi-nex-layouts', 'd3ad0627a29af168916ad574dadbca6759e2ac48', 'FF16-Nex-layouts-LICENSE.txt')):
        filename = 'LICENSE.txt' if repository == 'FF16Tools' else 'LICENSE'
        download(f'https://raw.githubusercontent.com/Nenkai/{repository}/{revision}/{filename}',
                 LICENSES / destination)
    dependencies = converter_dependencies(cli)
    with ThreadPoolExecutor(max_workers=4) as executor:
        notices = list(executor.map(nuget_notices, sorted(dependencies['packages'].items())))
    (LICENSES / 'converter-dependencies.json').write_text(json.dumps(notices, indent=2) + '\n', encoding='utf-8')
    # CPython's distribution includes the complete PSF and third-party notices.
    python_root = Path(sys.base_prefix)
    for filename in ('LICENSE.txt',):
        shutil.copyfile(python_root / filename, LICENSES / f'Python-{filename}')
    for filename in ('tcl/tk8.6/license.terms',):
        shutil.copyfile(python_root / filename, LICENSES / ('Tk-' + Path(filename).name))
    # Python LICENSE.txt covers the linked Tcl license, too; include current
    # upstream Tcl text explicitly to make the portable dependency set clear.
    download('https://raw.githubusercontent.com/tcltk/tcl/core-8-6-branch/license.terms', LICENSES / 'Tcl-license.terms')
    for filename in ('LICENSE.txt', 'ThirdPartyNotices.txt'):
        shutil.copyfile(dotnet / filename, LICENSES / f'dotnet-{filename}')


def build_python(prepare: bool) -> Path:
    python = ROOT / 'research/build-env/Scripts/python.exe'
    if not python.is_file() and prepare:
        venv.EnvBuilder(with_pip=True).create(python.parents[1])
    if not python.is_file():
        raise ValueError('Build environment missing. Run this script with --prepare-dependencies.')
    check = subprocess.run([str(python), '-c', 'import PyInstaller; print(PyInstaller.__version__)'],
                           capture_output=True, text=True)
    if check.returncode or check.stdout.strip() != PYINSTALLER_VERSION:
        if not prepare:
            raise ValueError('Pinned PyInstaller missing. Run with --prepare-dependencies.')
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                        f'pyinstaller=={PYINSTALLER_VERSION}'], check=True)
    return python


def collected_inputs(cli: Path, dotnet: Path) -> dict[str, Path]:
    if digest(cli) != FF16_CLI_SHA256:
        raise ValueError('Converter differs from the verified official 1.13.3 release')
    if not (dotnet / f'shared/Microsoft.NETCore.App/{DOTNET_VERSION}/coreclr.dll').is_file():
        raise ValueError('Bundled .NET runtime missing. Run with --prepare-dependencies.')
    if not (LICENSES / 'converter-dependencies.json').is_file():
        raise ValueError('Redistribution notices missing. Run with --prepare-dependencies.')
    verify_archive_contents(ROOT / 'vendor' / f'FF16Tools.CLI-{FF16_VERSION}-win-x64.zip',
                            cli.parent, FF16_ZIP_SHA256, prefix='win-x64/')
    verify_archive_contents(ROOT / 'vendor' / f'dotnet-runtime-{DOTNET_VERSION}-win-x64.zip',
                            dotnet, DOTNET_SHA512, 'sha512')
    result = {}

    def add(path: Path, destination: str) -> None:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing or symbolic-link bundle input: {path}')
        if destination in result:
            raise ValueError(f'Duplicate bundle input: {destination}')
        result[destination] = path.resolve()

    for directory in ('fftic/data', 'native/runtime', 'native/startup'):
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                add(path, path.relative_to(ROOT).as_posix())
    for relative in ('native/RuntimePatches.cpp', 'tools/build_native.ps1',
                     'tools/build_startup.ps1', 'THIRD_PARTY_NOTICES.txt', 'LICENSE'):
        add(ROOT / relative, relative)
    for path in sorted(cli.parent.rglob('*')):
        if path.is_file() and path.suffix.lower() != '.pdb':
            add(path, f'vendor/FF16Tools-{FF16_VERSION}/win-x64/' + path.relative_to(cli.parent).as_posix())
    for path in sorted(dotnet.rglob('*')):
        if path.is_file():
            add(path, 'vendor/dotnet/' + path.relative_to(dotnet).as_posix())
    for path in sorted(LICENSES.rglob('*')):
        if path.is_file():
            add(path, 'licenses/' + path.relative_to(LICENSES).as_posix())
    # No broad collection of project root, outputs, caches or game inputs.
    if any(name.startswith(('research/', 'outputs/')) or name.endswith('.pac') for name in result):
        raise ValueError('Private input reached executable bundle')
    return result


def collect_generator_notices(python: Path) -> None:
    """Retain authored dependency notices on every build, including offline builds."""
    LICENSES.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'fftic/data/RANDOMTOOLS-GPLv3.txt',
                    LICENSES / 'randomtools-GPLv3.txt')
    copying = python.parents[1] / 'Lib/site-packages' / f'pyinstaller-{PYINSTALLER_VERSION}.dist-info/licenses/COPYING.txt'
    if not copying.is_file():
        raise ValueError('Pinned PyInstaller distribution notice is missing')
    shutil.copyfile(copying, LICENSES / 'PyInstaller-COPYING.txt')
    apache = next(iter(sorted((LICENSES / 'converter-dependencies').rglob('Apache-2.0.txt'))), None)
    if apache is None:
        raise ValueError('Apache-2.0 text required by the PyInstaller runtime hooks is missing')
    shutil.copyfile(apache, LICENSES / 'PyInstaller-Apache-2.0.txt')


def validate_native_receipt() -> None:
    directory = ROOT / 'native/runtime'
    receipt = json.loads((directory / 'build.json').read_text(encoding='utf-8'))
    for source, script, binary, source_field, binary_field in (
            ('native/RuntimePatches.cpp', 'tools/build_native.ps1', 'fftic-rcc-runtime.dll', 'source_sha256', 'dll_sha256'),
            ('native/startup/RuntimeBridge.cs', 'tools/build_startup.ps1', 'fftic-rcc-startup.dll', 'bridge_source_sha256', 'bridge_dll_sha256')):
        key = hashlib.sha256((ROOT / source).read_bytes() + (ROOT / script).read_bytes()).hexdigest()
        if receipt[source_field] != key or receipt[binary_field] != digest(directory / binary):
            raise ValueError(f'Native bundled receipt mismatch: {binary}')


def write_spec(inputs: dict[str, Path], console: bool) -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    spec = BUILD / 'FFTIC Randomizer.spec'
    data = [(str(path), str(Path(destination).parent).replace('\\', '/'))
            for destination, path in sorted(inputs.items())]
    spec.write_text(
        '# Generated by tools/build_executable.py.\n'
        f'a = Analysis([{str(ROOT / "randomizer.py")!r}], pathex=[{str(ROOT)!r}], '
        f'binaries=[], datas={data!r}, hiddenimports=["tkinter", "tkinter.ttk"], '
        'hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)\n'
        'pyz = PYZ(a.pure)\n'
        'exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="FFTIC Randomizer", '
        f'debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console={console!r}, '
        'disable_windowed_traceback=False, argv_emulation=False, target_arch=None, '
        'codesign_identity=None, entitlements_file=None)\n', encoding='utf-8')
    return spec


def portable_package(target: Path, inputs: dict[str, Path]) -> Path:
    executable = target / 'FFTIC Randomizer.exe'
    shutil.copyfile(ROOT / 'LICENSE', target / 'LICENSE')
    shutil.copyfile(ROOT / 'THIRD_PARTY_NOTICES.txt', target / 'THIRD_PARTY_NOTICES.txt')
    shutil.copytree(LICENSES, target / 'licenses', dirs_exist_ok=True)
    (target / 'docs').mkdir(exist_ok=True)
    for filename in ('INSTALL.md', 'SETTINGS.md', 'LINUX.md'):
        shutil.copyfile(ROOT / 'docs' / filename, target / 'docs' / filename)
    readme = (
        f'FFTIC Randomizer {VERSION} — portable Windows x64 application\n\n'
        '1. Open FFTIC Randomizer.exe. Python, FF16Tools, and its runtime are included.\n'
        '2. Select the game folder containing FFT_enhanced.exe.\n'
        '3. Choose a seed and settings, then click Generate randomizer mod.\n'
        '4. Click Open output and install fftivc.randomizer.seed in Reloaded-II/Mods.\n'
        '5. Enable the seed and FFTIC Mod Loader, then launch Enhanced from Reloaded-II.\n\n'
        'Read docs/INSTALL.md for the complete first-time setup and troubleshooting.\n'
        'Read docs/SETTINGS.md for both ability modes and each setting.\n'
        'Use one active seed and a separate save slot. Close the game before changing seeds.\n\n'
        'Default seed output: Documents\\FFTIC Randomizer\\Seeds\n'
        'Reusable input caches: %LOCALAPPDATA%\\FFTIC Randomizer\n'
        'Folder choices and settings are not saved between launches in this version.\n\n'
        f'Source files: fftic-randomizer-{VERSION}-source.zip on the same Releases page.\n'
        'Downloads: https://github.com/Pyre-Flies/FFTIC-Randomizer/releases/latest\n'
        'Credits are available in About / Credits inside the app.\n')
    (target / 'README.txt').write_text(readme, encoding='utf-8')
    receipt = dict(generator_version=VERSION, pyinstaller_version=PYINSTALLER_VERSION,
                   python_version=sys.version.split()[0], platform='Windows x64', layout='onefile-windowed',
                   converter_version=FF16_VERSION, dotnet_version=DOTNET_VERSION,
                   executable_sha256=digest(executable),
                   sources={path.relative_to(ROOT).as_posix(): digest(path)
                            for path in [ROOT/'randomizer.py', ROOT/'tools/build_executable.py',
                                         *sorted((ROOT/'fftic').glob('*.py'))]},
                   resources={name: digest(path) for name, path in sorted(inputs.items())})
    (target / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    archive = ROOT / 'outputs' / f'fftic-randomizer-{VERSION}-windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(target.rglob('*')):
            if path.is_file():
                bundle.write(path, path.relative_to(target).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip():
            raise ValueError('Portable ZIP integrity check failed')
    (ROOT / 'outputs' / f'fftic-randomizer-{VERSION}-windows-x64-checksums.json').write_text(
        json.dumps({archive.name: digest(archive), f'{target.name}/{executable.name}': digest(executable)}, indent=2) + '\n',
        encoding='utf-8')
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-dependencies', action='store_true', help='Download pinned build/runtime/license dependencies into this project')
    parser.add_argument('--check-only', action='store_true', help='Prepare and verify inputs without compiling the final executable')
    parser.add_argument('--console', action='store_true', help='Diagnostic console build; default is the windowed GUI executable')
    parser.add_argument('--ff16tools', type=Path, default=ROOT / f'vendor/FF16Tools-{FF16_VERSION}/win-x64/FF16Tools.CLI.exe')
    parser.add_argument('--dotnet', type=Path, default=ROOT / 'vendor/dotnet')
    args = parser.parse_args()
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise ValueError('Build the Windows x64 application with 64-bit Windows Python')
    if args.prepare_dependencies:
        prepare_dependencies(args.ff16tools, args.dotnet)
    python = build_python(args.prepare_dependencies)
    collect_generator_notices(python)
    validate_native_receipt()
    inputs = collected_inputs(args.ff16tools, args.dotnet)
    print(f'Verified {len(inputs)} bundled resources ({sum(path.stat().st_size for path in inputs.values()):,} bytes).')
    if args.check_only:
        return 0
    target = ROOT / 'outputs' / f'FFTIC-Randomizer-{VERSION}'
    target.mkdir(parents=True, exist_ok=True)
    spec = write_spec(inputs, args.console)
    log = BUILD / 'build.log'
    with log.open('w', encoding='utf-8') as handle:
        build = subprocess.run([str(python), '-m', 'PyInstaller', '--noconfirm', '--clean',
                                '--distpath', str(target), '--workpath', str(BUILD / 'pyinstaller'), str(spec)],
                               cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
    if build.returncode:
        raise ValueError(f'Executable build failed; see {log}')
    archive = portable_package(target, inputs)
    print(f'Built: {target / "FFTIC Randomizer.exe"}')
    print(f'Portable package: {archive}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        raise SystemExit(1)
