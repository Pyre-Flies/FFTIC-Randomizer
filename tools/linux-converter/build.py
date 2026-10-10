"""Build a pinned, self-contained Linux x64 FF16Tools extraction converter.

Run with .NET SDK 9.0.318, git, CMake, and a C/C++ compiler installed. Sources
are fetched to research; only the requested output folder is packaged. This
never modifies a developer's FF16Tools checkout or any original game file.
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

from integration_test import test_converter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FF16_COMMIT = '14361aefa1e1265096b42cad95cd9f01550a0457'
FF16_VERSION = '1.13.3'
FF16_CODEC_SHA256 = '15a65380820e2b40e76daa9396a6d8334afda31be6114df371e3099229a61123'
FF16_CLI_PROJECT_SHA256 = '666b144bfcd31b7322219d83aaa3cb85a8eddf631489a44761e233628ebd4a2b'
DIRECTSTORAGE_COMMIT = 'c53f1499d5f67a61b69a1a348d22dcd2b4cb4ede'
LIBDEFLATE_COMMIT = '8ba9502fb30d2bf728592d121f0d402e40c8cb05'
FFTIC_LAYOUTS_COMMIT = 'd4a60952531d82bfd8a4fbb76b1f9b363f721dc1'
FF16_LAYOUTS_COMMIT = 'd3ad0627a29af168916ad574dadbca6759e2ac48'
DOTNET_VERSION = '9.0.20'
DOTNET_URL = ('https://builds.dotnet.microsoft.com/dotnet/Runtime/'
              f'{DOTNET_VERSION}/dotnet-runtime-{DOTNET_VERSION}-linux-x64.tar.gz')
DOTNET_SHA512 = ('aaa63e9156fcc9d1c51e15fb38e3c5388a7721ef1b64065c8865b03133906e9de'
                 '967ae33903c198c6acb9aa8bbae373e9001405074009c2ef2a0bb6e54b509a5')
ICU_VERSION = '72.1.0.3'
ICU_COMMIT = '807b1beec0dabf8a71f0bfde22da9705267f6a93'
ICU_PACKAGES = {
    'Microsoft.ICU.ICU4C.Runtime': 'cfe928e8740a3df636eaa09bd93d89126883f338f01b15e867f48704e6126449',
    'Microsoft.ICU.ICU4C.Runtime.linux-x64': '4afb3b4c2e79909ad7b531135f4b742b199c671ea9396ee4240f77f898ea5207',
}
ICU_FILES = {
    'libicudata.so.72.1.0.3': 'c1256eb44fdce1bda02d4cbb4ced3fd880fe972d7d80493229dd36feae401476',
    'libicui18n.so.72.1.0.3': '9f92ae6b8ef01fa64fcbee2fba51e43a443dc4f97242ff891af6ae3b318c730f',
    'libicuuc.so.72.1.0.3': '598cf8ecf444d6baffe3c7734ffa694d4913ced8669ecde0a78b2ad21d3dacb3',
}


def digest(path: Path, algorithm: str = 'sha256') -> str:
    return hashlib.new(algorithm, path.read_bytes()).hexdigest()


def run(command: list[str], *, cwd: Path | None = None,
        env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError(f'{command[0]} failed ({result.returncode}):\n{result.stdout}')
    return result.stdout


def checkout(url: str, commit: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.mkdir()
        run(['git', 'init', '--quiet', str(destination)])
        run(['git', '-C', str(destination), 'remote', 'add', 'origin', url])
        run(['git', '-C', str(destination), 'fetch', '--quiet', '--depth=1', 'origin', commit])
        run(['git', '-C', str(destination), 'checkout', '--quiet', '--detach', commit])
    if run(['git', '-C', str(destination), 'rev-parse', 'HEAD']).strip() != commit:
        raise ValueError(f'Source checkout differs from its pinned revision: {destination.name}')
    if run(['git', '-C', str(destination), 'remote', 'get-url', 'origin']).strip() != url:
        raise ValueError(f'Source remote differs from its pinned origin: {destination.name}')
    return destination


def submodule(source: Path, relative: str, expected: str) -> Path:
    run(['git', '-C', str(source), 'submodule', 'update', '--init', '--depth=1', relative])
    directory = source / relative
    if run(['git', '-C', str(directory), 'rev-parse', 'HEAD']).strip() != expected:
        raise ValueError(f'Submodule revision changed: {relative}')
    if run(['git', '-C', str(directory), 'status', '--porcelain', '--untracked-files=no']).strip():
        raise ValueError(f'Pinned submodule contains modified source: {relative}')
    return directory


def source_bytes(source: Path, commit: str, relative: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(source), 'show', f'{commit}:{relative}'])


def icu_project_overlay(original: bytes) -> bytes:
    text = original.decode('utf-8').replace('\r\n', '\n')
    if text.count('</Project>') != 1:
        raise ValueError('Pinned converter project has an unexpected XML structure')
    additions = (
        '  <!-- FFTIC Linux overlay: app-local full ICU; upstream source remains pinned. -->\n'
        '  <ItemGroup>\n'
        f'    <PackageReference Include="Microsoft.ICU.ICU4C.Runtime" Version="{ICU_VERSION}" />\n'
        f'    <RuntimeHostConfigurationOption Include="System.Globalization.AppLocalIcu" Value="{ICU_VERSION}" />\n'
        '    <RuntimeHostConfigurationOption Include="System.Globalization.Invariant" Value="false" />\n'
        '  </ItemGroup>\n'
    )
    return text.replace('</Project>', additions + '</Project>').encode('utf-8')


def overlay_converter(source: Path) -> dict:
    originals = {
        'FF16Tools.Shared/GDeflate.cs': FF16_CODEC_SHA256,
        'FF16Tools.CLI/FF16Tools.CLI.csproj': FF16_CLI_PROJECT_SHA256,
    }
    modified = run(['git', '-C', str(source), '-c', 'core.safecrlf=false',
                    'diff', '--name-only']).splitlines()
    if set(modified) - set(originals):
        raise ValueError('Converter checkout has changes outside the reviewed Linux overlays')
    receipt = {}
    for relative, expected_hash in originals.items():
        original = source_bytes(source, FF16_COMMIT, relative)
        if hashlib.sha256(original).hexdigest() != expected_hash:
            raise ValueError(f'Pinned converter source hash changed: {relative}')
        overlay = (HERE / 'GDeflate.cs').read_bytes() if relative.endswith('GDeflate.cs') else icu_project_overlay(original)
        existing = (source / relative).read_bytes()
        if existing.replace(b'\r\n', b'\n') not in (
                original.replace(b'\r\n', b'\n'), overlay.replace(b'\r\n', b'\n')):
            raise ValueError(f'Converter has unrelated local changes: {relative}')
        (source / relative).write_bytes(overlay)
        receipt[relative] = dict(original_sha256=expected_hash,
                                overlay_sha256=hashlib.sha256(overlay).hexdigest())
    probe_source = HERE / 'GlobalizationProbe.cs'
    probe_target = source / 'FF16Tools.CLI/FFTICGlobalizationProbe.cs'
    if probe_target.exists() and probe_target.read_bytes() != probe_source.read_bytes():
        raise ValueError('Converter globalization probe has unrelated local changes')
    shutil.copyfile(probe_source, probe_target)
    receipt['FF16Tools.CLI/FFTICGlobalizationProbe.cs'] = dict(authored_sha256=digest(probe_source))
    return receipt


def notice_module():
    spec = importlib.util.spec_from_file_location('fftic_converter_notice_helpers',
                                                ROOT / 'tools/build_executable.py')
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def layout_aliases(output: Path) -> int:
    """Keep upstream spelling plus lowercase aliases used by native NXD names.

    The original reader relies on Windows' case-insensitive filesystem. Copying
    identical layout bytes under lowercase names preserves that lookup contract
    on Linux without changing upstream parsing or table-name metadata.
    """
    layouts = output / 'Nex/Layouts'
    count = 0
    if not layouts.is_dir():
        raise ValueError('Published converter is missing its Nex layouts')
    for source in sorted(layouts.rglob('*.layout')):
        destination = source.with_name(source.name.lower())
        if destination == source:
            continue
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            raise ValueError(f'Layout filename case collision: {source.name}')
        shutil.copyfile(source, destination)
        count += 1
    return count


def omit_optional_trace_provider(output: Path) -> list[dict]:
    """Omit .NET's optional LTTng plugin, retaining the normal CLR runtime.

    The pinned runtime's PAL_InitializeTracing explicitly accepts dlopen failure
    when the provider or its tracing dependencies are unavailable. Keeping this
    unused plugin would impose an unnecessary liblttng-ust.so.0 dependency on
    Steam Deck and desktop users.
    """
    provider = output / 'libcoreclrtraceptprovider.so'
    if not provider.exists():
        return []
    if not provider.is_file() or provider.is_symlink():
        raise ValueError('Optional runtime trace provider is not a regular file')
    record = dict(file=provider.name, original_sha256=digest(provider),
                  reason='Optional LTTng tracing plugin; the CLR continues when it cannot be loaded',
                  upstream_source='https://github.com/dotnet/runtime/blob/v9.0.20/src/coreclr/pal/src/misc/tracepointprovider.cpp')
    provider.unlink()
    return [record]


def validate_app_local_icu(output: Path) -> dict:
    runtime = json.loads((output / 'FF16Tools.CLI.runtimeconfig.json').read_text(encoding='utf-8'))
    properties = runtime['runtimeOptions'].get('configProperties', {})
    if properties.get('System.Globalization.AppLocalIcu') != ICU_VERSION:
        raise ValueError('Published converter is not configured for its pinned app-local ICU')
    if properties.get('System.Globalization.Invariant') is not False:
        raise ValueError('Published converter does not explicitly preserve full globalization')
    version_requirements = set()
    for filename, expected in ICU_FILES.items():
        path = output / filename
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            raise ValueError(f'Published ICU binary differs from its pinned official package: {filename}')
        binary = path.read_bytes()
        if binary[:6] != b'\x7fELF\x02\x01' or int.from_bytes(binary[18:20], 'little') != 62:
            raise ValueError(f'Published ICU binary is not Linux x64: {filename}')
        version_requirements.update(match.decode('ascii') for match in re.findall(rb'GLIBC_[0-9.]+', binary))
    maximum = max(version_requirements, key=lambda value: tuple(map(int, value.split('_')[1].split('.'))))
    if tuple(map(int, maximum.split('_')[1].split('.'))) > (2, 35):
        raise ValueError('Bundled ICU exceeds the Ubuntu 22.04 glibc baseline')
    return dict(package='Microsoft.ICU.ICU4C.Runtime', version=ICU_VERSION,
                source_commit=ICU_COMMIT, files=dict(ICU_FILES), full_globalization=True,
                invariant_mode=False, highest_glibc_requirement=maximum,
                runtimeconfig_property='System.Globalization.AppLocalIcu')


def record_icu_sources(output: Path) -> None:
    for package, expected in ICU_PACKAGES.items():
        archive = ROOT / 'vendor/executable-licenses/nuget' / f'{package}.{ICU_VERSION}.nupkg'
        if digest(archive) != expected:
            raise ValueError(f'ICU package archive differs from its pinned official download: {package}')
        with zipfile.ZipFile(archive) as bundle:
            version_info = bundle.read('version.txt').decode('utf-8-sig')
            if f'MS-ICU = {ICU_VERSION}' not in version_info or f'commit = {ICU_COMMIT}' not in version_info:
                raise ValueError(f'ICU source provenance changed: {package}')
    text = (
        f'Microsoft ICU runtime package: {ICU_VERSION}\n'
        f'Source: https://github.com/microsoft/icu/tree/{ICU_COMMIT}\n'
        f'Release: https://github.com/microsoft/icu/releases/tag/v{ICU_VERSION}\n'
        'Configuration: https://learn.microsoft.com/en-us/dotnet/core/extensions/globalization-icu#app-local-icu\n'
        'The complete Unicode/ICU and included third-party notices are retained\n'
        'in converter-dependencies/Microsoft.ICU.ICU4C.Runtime*/LICENSE.\n'
        'The unmodified native libraries are bundled beside the converter.\n'
        'Globalization invariant mode is disabled.\n\n'
        'Pinned official package archive SHA256 values:\n'
    )
    text += ''.join(f'{name}/{ICU_VERSION}: {value}\n' for name, value in ICU_PACKAGES.items())
    (output / 'licenses/ICU-SOURCES.txt').write_text(text, encoding='utf-8')


def verify_notice_archive(notice: dict, assets: dict) -> dict:
    """Link notice ZIP bytes to the packages actually restored by NuGet.

    NuGet's dependency hash is an unsigned-content hash for signed packages,
    whereas .nupkg.sha512 covers the full archive, including its signature.
    Check these distinct hashes against their corresponding restore receipts;
    never compare the dependency content hash with the raw ZIP hash.
    """
    identity = notice['package']
    name, version = identity.rsplit('/', 1)
    expected = notice.get('dependency_sha512')
    if not expected or not expected.startswith('sha512-'):
        raise ValueError(f'Restored dependency content hash missing: {identity}')
    content_hash = expected.removeprefix('sha512-')
    libraries = {key.casefold(): value for key, value in assets['libraries'].items()}
    library = libraries.get(identity.casefold())
    if not library or library.get('type') != 'package' or library.get('sha512') != content_hash:
        raise ValueError(f'Published dependency differs from its restore metadata: {identity}')
    relative = Path(library['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError(f'Invalid restored package path: {identity}')
    downloaded = ROOT / 'vendor/executable-licenses/nuget' / f'{name}.{version}.nupkg'
    downloaded_hash = base64.b64encode(hashlib.sha512(downloaded.read_bytes()).digest()).decode('ascii')
    found = False
    for package_root in assets['packageFolders']:
        directory = Path(package_root) / relative
        basename = f'{name.lower()}.{version.lower()}.nupkg'
        archive = directory / basename
        archive_hash_file = directory / (basename + '.sha512')
        metadata_file = directory / '.nupkg.metadata'
        if not all(path.is_file() for path in (archive, archive_hash_file, metadata_file)):
            continue
        metadata = json.loads(metadata_file.read_text(encoding='utf-8-sig'))
        if metadata.get('contentHash') != content_hash:
            raise ValueError(f'Cached NuGet content hash differs from restored dependency: {identity}')
        archive_hash = base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode('ascii')
        if archive_hash_file.read_text(encoding='utf-8-sig').strip() != archive_hash:
            raise ValueError(f'Cached NuGet archive failed its raw SHA512 receipt: {identity}')
        if downloaded_hash != archive_hash:
            raise ValueError(f'Official notice archive differs from the restored NuGet archive: {identity}')
        found = True
        break
    if not found:
        raise ValueError(f'Restored NuGet archive and receipts missing: {identity}')
    return dict(package_archive_sha512='sha512-' + downloaded_hash,
                restored_content_sha512=expected,
                archive_verification='official archive bytes match the restored NuGet archive and its raw SHA512 receipt',
                content_verification='published dependency, project assets and NuGet contentHash receipt match')


def collect_notices(output: Path, converter: Path, directstorage: Path,
                    libdeflate: Path, work: Path) -> dict:
    helpers = notice_module()
    licenses = output / 'licenses'
    licenses.mkdir(exist_ok=True)
    helpers.LICENSES = licenses
    deps = json.loads((output / 'FF16Tools.CLI.deps.json').read_text(encoding='utf-8'))
    packages = {name: value for name, value in deps['libraries'].items()
                if value.get('type') == 'package'}
    with ThreadPoolExecutor(max_workers=4) as executor:
        notices = list(executor.map(helpers.nuget_notices, sorted(packages.items())))
    assets = json.loads((converter / 'FF16Tools.CLI/obj/project.assets.json').read_text(encoding='utf-8-sig'))
    for notice in notices:
        notice.update(verify_notice_archive(notice, assets))
    (licenses / 'converter-dependencies.json').write_text(json.dumps(notices, indent=2) + '\n', encoding='utf-8')
    for source, filename in (
            (converter / 'LICENSE.txt', 'FF16Tools-LICENSE.txt'),
            (converter / 'FF16Tools.Files/Nex/Layouts/ffto/LICENSE', 'FFTIC-Nex-layouts-LICENSE.txt'),
            (converter / 'FF16Tools.Files/Nex/Layouts/faith/LICENSE', 'FF16-Nex-layouts-LICENSE.txt'),
            (directstorage / 'LICENSE', 'DirectStorage-MIT-LICENSE.txt'),
            (directstorage / 'GDeflate/GDeflate/LICENSE', 'GDeflate-Apache-2.0-LICENSE.txt'),
            (libdeflate / 'COPYING', 'NVIDIA-libdeflate-COPYING.txt')):
        shutil.copyfile(source, licenses / filename)
    runtime = helpers.download(DOTNET_URL, work / f'dotnet-runtime-{DOTNET_VERSION}-linux-x64.tar.gz',
                               DOTNET_SHA512, 'sha512')
    with tarfile.open(runtime, 'r:gz') as archive:
        for filename in ('LICENSE.txt', 'ThirdPartyNotices.txt'):
            members = [item for item in archive.getmembers()
                       if item.name.lstrip('./') == filename and item.isfile()]
            if len(members) != 1:
                raise ValueError(f'Official .NET runtime notice missing: {filename}')
            stream = archive.extractfile(members[0])
            assert stream is not None
            (licenses / f'dotnet-{filename}').write_bytes(stream.read())
    return dict(package_count=len(notices), runtime_notices_sha512=DOTNET_SHA512)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work', type=Path, default=ROOT / 'research/linux-converter-build')
    args = parser.parse_args()
    if sys.platform != 'linux' or platform.machine().lower() not in {'x86_64', 'amd64'}:
        raise ValueError('Build the release converter on Linux x64; native CMake tests can also run on Windows.')
    for command in ('git', 'cmake', 'dotnet'):
        if shutil.which(command) is None:
            raise ValueError(f'Build dependency missing: {command}')
    work = args.work.resolve()
    output = args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    sdk_settings = {'sdk': {'version': '9.0.318', 'rollForward': 'disable',
                            'allowPrerelease': False}}
    sdk_config = work / 'global.json'
    if sdk_config.is_file() and json.loads(sdk_config.read_text(encoding='utf-8')) != sdk_settings:
        raise ValueError('Converter build work folder has an unrelated global.json')
    sdk_config.write_text(json.dumps(sdk_settings, indent=2) + '\n', encoding='utf-8')
    # .NET selects the SDK from the working directory, even for an absolute
    # project path. A newer SDK on a developer machine or hosted runner must
    # not silently replace the pinned build compiler.
    sdk_version = run(['dotnet', '--version'], cwd=work).strip()
    if sdk_version != '9.0.318':
        raise ValueError(f'Use pinned .NET SDK 9.0.318; detected {sdk_version}')
    notice_tests = run([sys.executable, '-m', 'unittest', 'discover', '-s', str(HERE),
                        '-p', 'test_package_notices.py', '-v'], cwd=work)
    (work / 'notice-tests.txt').write_text(notice_tests, encoding='utf-8')
    output.mkdir(parents=True, exist_ok=True)
    converter = checkout('https://github.com/Nenkai/FF16Tools.git', FF16_COMMIT, work / 'FF16Tools')
    submodule(converter, 'FF16Tools.Files/Nex/Layouts/ffto', FFTIC_LAYOUTS_COMMIT)
    submodule(converter, 'FF16Tools.Files/Nex/Layouts/faith', FF16_LAYOUTS_COMMIT)
    overlays = overlay_converter(converter)
    directstorage = checkout('https://github.com/microsoft/DirectStorage.git',
                            DIRECTSTORAGE_COMMIT, work / 'DirectStorage')
    if run(['git', '-C', str(directstorage), 'status', '--porcelain', '--untracked-files=no']).strip():
        raise ValueError('Pinned DirectStorage source contains local modifications')
    libdeflate = submodule(directstorage, 'GDeflate/3rdparty/libdeflate', LIBDEFLATE_COMMIT)
    native = work / 'native'
    run(['cmake', '-S', str(HERE), '-B', str(native), '-DCMAKE_BUILD_TYPE=Release',
         f'-DDIRECTSTORAGE_SOURCE={directstorage}'])
    run(['cmake', '--build', str(native), '--config', 'Release', '--parallel', '2'])
    native_result = run(['ctest', '--test-dir', str(native), '--build-config', 'Release', '--output-on-failure'])
    fixtures = work / 'fixtures'
    fixture_result = run([str(native / 'fftic_gdeflate_test'), '--fixtures', str(fixtures)])
    test_env = dict(os.environ)
    test_env['LD_LIBRARY_PATH'] = str(native) + ':' + test_env.get('LD_LIBRARY_PATH', '')
    managed_result = run(['dotnet', 'run', '--project', str(HERE / 'managed-test/CodecTest.csproj'),
                          '--configuration', 'Release', '--', str(fixtures)], cwd=work, env=test_env)
    (work / 'codec-tests.txt').write_text(native_result + fixture_result + managed_result, encoding='utf-8')
    publish_result = run(['dotnet', 'publish', str(converter / 'FF16Tools.CLI/FF16Tools.CLI.csproj'),
                         '--configuration', 'Release', '--runtime', 'linux-x64',
                         '--self-contained', 'true', '--output', str(output),
                         '-p:RuntimeFrameworkVersion=' + DOTNET_VERSION,
                         '-p:PublishSingleFile=false', '-p:UseAppHost=true',
                         '-p:DebugSymbols=false', '-p:DebugType=None'], cwd=work)
    (work / 'publish.txt').write_text(publish_result, encoding='utf-8')
    omitted_runtime = omit_optional_trace_provider(output)
    shutil.copyfile(native / 'libfftic_gdeflate.so', output / 'libfftic_gdeflate.so')
    aliases = layout_aliases(output)
    app_local_icu = validate_app_local_icu(output)
    executable = output / 'FF16Tools.CLI'
    apphost_header = executable.read_bytes()[:20]
    if (apphost_header[:6] != b'\x7fELF\x02\x01' or
            int.from_bytes(apphost_header[18:20], 'little') != 62):
        raise ValueError('Published converter does not have a Linux x64 ELF apphost')
    cli_result = run([str(executable), '--help'], cwd=output)
    if 'unpack' not in cli_result.lower() or 'nxd-to-sqlite' not in cli_result.lower():
        raise ValueError('Published converter help did not expose expected conversion commands')
    (work / 'converter-help.txt').write_text(cli_result, encoding='utf-8')
    integration = test_converter(executable, fixtures, work / 'integration')
    dependencies = collect_notices(output, converter, directstorage, libdeflate, work)
    record_icu_sources(output)
    for debug in output.rglob('*.pdb'):
        debug.unlink()
    inputs = {path.relative_to(HERE).as_posix(): digest(path) for path in sorted(HERE.rglob('*'))
              if path.is_file() and path.suffix in {'.py', '.cpp', '.h', '.cs', '.csproj', '.txt'}
              and not set(path.relative_to(HERE).parts) & {'obj', 'bin', '__pycache__'}}
    receipt = dict(platform='linux-x64', converter_version=FF16_VERSION,
                   ff16tools_commit=FF16_COMMIT, directstorage_commit=DIRECTSTORAGE_COMMIT,
                   libdeflate_commit=LIBDEFLATE_COMMIT, fftic_layouts_commit=FFTIC_LAYOUTS_COMMIT,
                   ff16_layouts_commit=FF16_LAYOUTS_COMMIT, dotnet_sdk=sdk_version,
                   dotnet_runtime=DOTNET_VERSION, codec='bounded Microsoft/NVIDIA CPU GDeflate',
                   extraction_only=True, synthetic_fixtures=24, tests_passed=True,
                   converter_integration=integration,
                   lowercase_layout_aliases=aliases,
                   notice_verification_tests=6,
                   omitted_optional_runtime_components=omitted_runtime,
                   app_local_icu=app_local_icu, converter_overlays=overlays,
                   notice_packages=dependencies['package_count'],
                   runtime_notices_sha512=dependencies['runtime_notices_sha512'], sources=inputs,
                   files={path.relative_to(output).as_posix(): digest(path)
                          for path in sorted(output.rglob('*')) if path.is_file()
                          and path.name != 'build-receipt.json'})
    (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(f'Built native Linux x64 converter; {len(receipt["files"])} files, 24 codec fixtures passed.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        raise SystemExit(1)
