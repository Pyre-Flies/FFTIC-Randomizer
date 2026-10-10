"""Build native Linux x64 AppImage and portable bundles on Ubuntu 22.04.

Python/Tk and a self-contained Linux FF16Tools converter are bundled. The
Windows mod DLLs are resource files for the game running through Proton; they
are never loaded by this Linux application. No game files enter either bundle.

Build host packages: python3-venv, python3-tk, build-essential, cmake, git,
patchelf, squashfs-tools, xvfb, xauth, libicu70, libssl3 and zlib1g. A .NET 9
SDK is required only while building the converter. CI pins SDK 9.0.318.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import venv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fftic import VERSION

PYINSTALLER_VERSION = "6.22.3"
APPIMAGETOOL_VERSION = "1.9.1"
APPIMAGETOOL_SHA256 = "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
APPIMAGE_RUNTIME_SHA256 = "156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074"
APPIMAGE_RUNTIME_ASSET = "https://api.github.com/repos/AppImage/type2-runtime/releases/assets/596078161"
APPIMAGE_RUNTIME_COMMIT = "8f39b89e2ac31e1640b3d3f7e9a5108e6ce805fa"
NO_ICU_BASE_IMAGE = "ubuntu@sha256:5ec03bb3441e8b0bf3b4f9cd4629a1ae763010dc3035bb8da3ae6cf026486401"
APP_LOCAL_ICU_VERSION = "72.1.0.3"
BUILD = ROOT / "research/linux-build"
FF16_VERSION = "1.13.3"
CONVERTER_DESTINATION = f"vendor/FF16Tools-{FF16_VERSION}/linux-x64"
RUNTIME_NOTICES = (
    (f"https://raw.githubusercontent.com/AppImage/type2-runtime/{APPIMAGE_RUNTIME_COMMIT}/LICENSE", "AppImage-runtime-LICENSE.txt", "aa154fc9070614bbe7921f89db11efd1dba7a1f3a41685958110e2230f9c0ca1"),
    ("https://raw.githubusercontent.com/libfuse/libfuse/fuse-3.15.0/LGPL2.txt", "libfuse-LGPL2.txt", "dc626520dcd53a22f727af3ee42c770e56c97a64fe3adb063799d8ab032fe551"),
    ("https://raw.githubusercontent.com/libfuse/libfuse/fuse-3.15.0/GPL2.txt", "libfuse-GPL2.txt", "8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643"),
    ("https://raw.githubusercontent.com/vasi/squashfuse/0.5.2/LICENSE", "squashfuse-LICENSE.txt", "9e909cc8a8ba27b1a649c964cf9eda37de911f3138c2b64e6d2f01703904ac13"),
    ("https://git.musl-libc.org/cgit/musl/plain/COPYRIGHT?h=v1.2.5", "musl-COPYRIGHT.txt", "f9bc4423732350eb0b3f7ed7e91d530298476f8fec0c6c427a1c04ade22655af"),
    ("https://raw.githubusercontent.com/facebook/zstd/v1.5.7/LICENSE", "zstd-LICENSE.txt", "7055266497633c9025b777c78eb7235af13922117480ed5c674677adc381c9d8"),
    ("https://raw.githubusercontent.com/madler/zlib/v1.3.1/LICENSE", "zlib-LICENSE.txt", "845efc77857d485d91fb3e0b884aaa929368c717ae8186b66fe1ed2495753243"),
    (f"https://codeload.github.com/AppImage/type2-runtime/tar.gz/{APPIMAGE_RUNTIME_COMMIT}", "AppImage-runtime-source.tar.gz", "c449eb42c2190820872631f5e22f8e15b1e985a36dc4a9e2de3585bb7536c785"),
    ("https://github.com/libfuse/libfuse/releases/download/fuse-3.15.0/fuse-3.15.0.tar.xz", "libfuse-3.15.0-source.tar.xz", "70589cfd5e1cff7ccd6ac91c86c01be340b227285c5e200baa284e401eea2ca0"),
    ("https://github.com/vasi/squashfuse/archive/0.5.2.tar.gz", "squashfuse-0.5.2-source.tar.gz", "db0238c5981dabbd80ee09ae15387f390091668ca060a7bc38047912491443d3"),
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def download(url: str, target: Path, expected: str) -> Path:
    if target.is_file() and digest(target) == expected:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "FFTIC-Randomizer-build", "Accept": "application/octet-stream"})
    with urllib.request.urlopen(request, timeout=120) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError(f"Downloaded packaging dependency failed its pinned hash: {url}")
    target.write_bytes(content)
    target.chmod(0o755)
    return target


def run(command: list[str], *, cwd: Path = ROOT, environment: dict | None = None, log: Path | None = None, timeout: int | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout)
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise ValueError(f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stdout[-6000:]}")
    return result


def build_python(prepare: bool) -> Path:
    python = BUILD / "python/bin/python"
    if not python.is_file() and prepare:
        venv.EnvBuilder(with_pip=True).create(python.parents[1])
    if not python.is_file():
        raise ValueError("Build environment missing; run with --prepare-dependencies")
    check = subprocess.run([str(python), "-c", "import PyInstaller; print(PyInstaller.__version__)"], capture_output=True, text=True)
    if check.returncode or check.stdout.strip() != PYINSTALLER_VERSION:
        if not prepare:
            raise ValueError("Pinned PyInstaller missing; run with --prepare-dependencies")
        run([str(python), "-m", "pip", "install", "--disable-pip-version-check", f"pyinstaller=={PYINSTALLER_VERSION}"], log=BUILD / "python-dependencies.log")
    run([str(python), "-c", "import tkinter; print(tkinter.TkVersion)"], log=BUILD / "tk-version.log")
    return python


def validate_native_receipt() -> None:
    directory = ROOT / "native/runtime"
    receipt = json.loads((directory / "build.json").read_text(encoding="utf-8"))
    for source, script, binary, source_field, binary_field in (
            ("native/RuntimePatches.cpp", "tools/build_native.ps1", "fftic-rcc-runtime.dll", "source_sha256", "dll_sha256"),
            ("native/startup/RuntimeBridge.cs", "tools/build_startup.ps1", "fftic-rcc-startup.dll", "bridge_source_sha256", "bridge_dll_sha256")):
        source_hash = hashlib.sha256((ROOT / source).read_bytes() + (ROOT / script).read_bytes()).hexdigest()
        if receipt[source_field] != source_hash or receipt[binary_field] != digest(directory / binary):
            raise ValueError(f"Windows mod resource receipt mismatch: {binary}")


def collect_inputs(converter: Path, licenses: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}

    def add(path: Path, name: str) -> None:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or symbolic resource input: {path}")
        if name in result:
            raise ValueError(f"Duplicate bundle resource: {name}")
        result[name] = path.resolve()

    for directory in ("fftic/data", "native/runtime", "native/startup"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix.lower() not in {".pyc", ".pdb"}:
                add(path, path.relative_to(ROOT).as_posix())
    for name in ("native/RuntimePatches.cpp", "tools/build_native.ps1", "tools/build_startup.ps1", "LICENSE", "THIRD_PARTY_NOTICES.txt"):
        add(ROOT / name, name)
    for path in sorted(converter.rglob("*")):
        if path.is_file() and path.suffix.lower() not in {".pdb", ".pac", ".sqlite"}:
            add(path, f"{CONVERTER_DESTINATION}/{path.relative_to(converter).as_posix()}")
    for path in sorted(licenses.rglob("*")):
        if path.is_file():
            add(path, f"licenses/{path.relative_to(licenses).as_posix()}")
    for name in result:
        if name.startswith(("research/", "outputs/")) or name.lower().endswith((".pac", ".nxd", ".sqlite", ".pdb")):
            raise ValueError(f"Non-distributable game/cache input reached the bundle: {name}")
    executable = converter / "FF16Tools.CLI"
    codec = converter / "libfftic_gdeflate.so"
    for path in (executable, codec):
        if not path.is_file() or path.read_bytes()[:4] != b"\x7fELF":
            raise ValueError(f"Expected a native Linux converter component: {path}")
    for name in ("libcoreclr.so", "FF16Tools.CLI.runtimeconfig.json", "build-receipt.json"):
        if not (converter / name).is_file():
            raise ValueError(f"Self-contained converter input missing: {name}")
    runtime_options = json.loads((converter / "FF16Tools.CLI.runtimeconfig.json").read_text(encoding="utf-8"))["runtimeOptions"]
    if (runtime_options.get("framework") or runtime_options.get("frameworks")
            or not any(item.get("name") == "Microsoft.NETCore.App" and item.get("version") == "9.0.20"
                       for item in runtime_options.get("includedFrameworks", []))):
        raise ValueError("Converter runtime configuration requires a global framework or differs from pinned self-contained .NET")
    globalization = runtime_options.get("configProperties", {})
    if (globalization.get("System.Globalization.AppLocalIcu") != APP_LOCAL_ICU_VERSION
            or globalization.get("System.Globalization.Invariant") is not False):
        raise ValueError("Converter must use the pinned app-local ICU with full Unicode globalization")
    for name in ("libicudata", "libicuuc", "libicui18n"):
        library = converter / f"{name}.so.{APP_LOCAL_ICU_VERSION}"
        if not library.is_file() or library.read_bytes()[:4] != b"\x7fELF":
            raise ValueError(f"Bundled ICU library missing: {library.name}")
    receipt = json.loads((converter / "build-receipt.json").read_text(encoding="utf-8"))
    if (receipt.get("platform") != "linux-x64" or receipt.get("converter_version") != FF16_VERSION
            or receipt.get("dotnet_runtime") != "9.0.20" or receipt.get("tests_passed") is not True
            or receipt.get("synthetic_fixtures") != 24):
        raise ValueError("Converter build receipt does not describe the tested pinned Linux converter")
    expected = receipt.get("files", {})
    actual = {path.relative_to(converter).as_posix(): digest(path) for path in sorted(converter.rglob("*"))
              if path.is_file() and path.name != "build-receipt.json"}
    if not expected or expected != actual:
        raise ValueError("Published Linux converter differs from its build receipt")
    return result


def collect_notices(python: Path, converter: Path, prepare: bool) -> Path:
    licenses = BUILD / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    dependency_licenses = converter / "licenses"
    if not dependency_licenses.is_dir() or not any(dependency_licenses.rglob("*")):
        raise ValueError("Linux converter dependency notices are missing")
    shutil.copytree(dependency_licenses, licenses / "converter", dirs_exist_ok=True)
    shutil.copyfile(ROOT / "fftic/data/RANDOMTOOLS-GPLv3.txt", licenses / "randomtools-GPLv3.txt")
    # Debian/Ubuntu packages supply the complete CPython/Tcl/Tk notices.
    for package in ("python3.10", "libpython3.10-stdlib", "tcl8.6", "tk8.6"):
        copyright_file = Path("/usr/share/doc") / package / "copyright"
        if not copyright_file.is_file():
            raise ValueError(f"Build-host dependency notice missing: {copyright_file}")
        shutil.copyfile(copyright_file, licenses / f"{package}-copyright.txt")
    metadata = run([str(python), "-c", "import importlib.metadata; print(importlib.metadata.distribution('pyinstaller')._path)" ]).stdout.strip()
    distribution = Path(metadata)
    notices = sorted(path for path in distribution.rglob("*") if path.is_file() and path.name.lower() in {"copying.txt", "license.txt"})
    if not notices:
        raise ValueError("PyInstaller notices are missing")
    for path in notices:
        shutil.copyfile(path, licenses / ("PyInstaller-" + path.name))
    for path in sorted(distribution.rglob("*")):
        if path.is_file() and "license" in path.name.lower() and path not in notices:
            shutil.copyfile(path, licenses / ("PyInstaller-" + path.name))
    runtime_notices = licenses / "AppImage-runtime"
    for url, name, expected in RUNTIME_NOTICES:
        target = runtime_notices / name
        if prepare:
            download(url, target, expected)
        if not target.is_file() or digest(target) != expected:
            raise ValueError(f"Pinned AppImage runtime notice/source is missing: {name}; use --prepare-dependencies")
    (runtime_notices / "SOURCES.txt").write_text(
        f"AppImage runtime source: https://github.com/AppImage/type2-runtime/tree/{APPIMAGE_RUNTIME_COMMIT}\n"
        "The unmodified runtime source archive and its exact libfuse/squashfuse source\n"
        "archives are included beside this file. The runtime source contains its\n"
        "build scripts and libfuse patch, allowing the static runtime to be rebuilt.\n"
        "Additional upstream library source: https://git.musl-libc.org/cgit/musl/\n"
        "https://github.com/facebook/zstd and https://github.com/madler/zlib\n",
        encoding="utf-8")
    return licenses


SMOKE_ENTRYPOINT = '''"""Generated Linux entry point; diagnostic mode contains no game data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import types

if sys.argv[1:2] == ["--bundle-smoke"]:
    from fftic import VERSION
    from fftic.runtime import workspace_root, resource_root, converter_environment
    from fftic.preview import locate_cli, run_cli
    from fftic.gui import create_app
    resource = resource_root()
    cli = locate_cli(workspace_root())
    for name in ("native/runtime/fftic-rcc-runtime.dll", "native/runtime/fftic-rcc-startup.dll", "native/runtime/build.json", "fftic/data/rcc-conditionals.json", "THIRD_PARTY_NOTICES.txt", "LICENSE"):
        assert (resource / name).is_file(), name
    assert cli.read_bytes()[:4] == b"\\x7fELF"
    result = subprocess.run([str(cli), "--help"], cwd=cli.parent, env=converter_environment(), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FF16Tools" in result.stdout + result.stderr
    integration = {}
    if len(sys.argv) == 4:
        module = types.ModuleType("fftic_frozen_converter_integration")
        exec(__INTEGRATION_SOURCE__, module.__dict__)
        module.run_cli = lambda executable, arguments, work, name: run_cli(executable, arguments, work / (name + ".log"))
        integration = module.test_converter(cli, Path(sys.argv[2]), Path(sys.argv[3]))
    app = create_app(workspace_root())
    app.update_idletasks()
    title, geometry = app.title(), app.geometry()
    assert title == "FFTIC Randomizer", title
    assert app.winfo_children(), "GUI has no controls"
    app.after(250, app.destroy)
    app.mainloop()
    print(json.dumps(dict(result="passed", version=VERSION, gui_title=title, gui_geometry=geometry,
                         converter=str(cli.relative_to(resource)), converter_help="passed",
                         converter_integration=integration, bundled_mod_resources="passed", global_dotnet_required=False)))
    sys.exit(0)

from randomizer import main
sys.exit(main())
'''


def write_spec(inputs: dict[str, Path]) -> Path:
    entry = BUILD / "entrypoint.py"
    integration_source = (ROOT / "tools/linux-converter/integration_test.py").read_text(encoding="utf-8")
    entry.write_text(SMOKE_ENTRYPOINT.replace("__INTEGRATION_SOURCE__", repr(integration_source)), encoding="utf-8")
    spec = BUILD / "FFTICRandomizer.spec"
    data = [(str(path), Path(name).parent.as_posix()) for name, path in sorted(inputs.items())]
    spec.write_text(
        f"a = Analysis([{str(entry)!r}], pathex=[{str(ROOT)!r}], binaries=[], datas={data!r}, "
        "hiddenimports=['tkinter', 'tkinter.ttk', '__future__', 'argparse', 'contextlib', 'sqlite3', 'struct', 'zlib'], "
        "hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)\n"
        "pyz = PYZ(a.pure)\n"
        "exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FFTICRandomizer', debug=False, "
        "bootloader_ignore_signals=False, strip=False, upx=False, console=True)\n"
        "coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FFTICRandomizer')\n", encoding="utf-8")
    return spec


def elf_paths(folder: Path) -> list[Path]:
    selected = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                if stream.read(4) == b"\x7fELF":
                    selected.append(path)
    return selected


def inspect_native_dependencies(folder: Path, converter: Path, licenses: Path) -> dict:
    libraries = folder / "_internal"
    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = os.pathsep.join((str(libraries), str(converter)))
    dependencies: dict[str, list[str]] = {}
    maximum_glibc = (0, 0)

    def retain_system_notice(library: Path) -> None:
        if not library.is_file():
            return
        owner = subprocess.run(["dpkg-query", "-S", str(library)], capture_output=True, text=True)
        if owner.returncode and str(library).startswith("/lib/"):
            owner = subprocess.run(["dpkg-query", "-S", "/usr" + str(library)], capture_output=True, text=True)
        if owner.returncode:
            return
        package = owner.stdout.split(": ", 1)[0].split(":", 1)[0]
        notice = Path("/usr/share/doc") / package / "copyright"
        if notice.is_file():
            (licenses / "system-libraries").mkdir(exist_ok=True)
            shutil.copyfile(notice, licenses / "system-libraries" / f"{package}-copyright.txt")

    for path in elf_paths(folder):
        version_info = subprocess.run(["readelf", "--version-info", str(path)], capture_output=True, text=True)
        for major, minor in re.findall(r"GLIBC_(\d+)\.(\d+)", version_info.stdout):
            maximum_glibc = max(maximum_glibc, (int(major), int(minor)))
        linked = subprocess.run(["ldd", str(path)], capture_output=True, text=True, env=environment)
        output = linked.stdout + linked.stderr
        if "not found" in output:
            raise ValueError(f"Unresolved Linux dependency for {path}:\n{output}")
        if linked.returncode and "not a dynamic executable" not in output and "statically linked" not in output:
            raise ValueError(f"Could not inspect ELF dependencies for {path}:\n{output}")
        dependencies[path.relative_to(folder).as_posix()] = output.splitlines()
        for prefix in ("/lib/x86_64-linux-gnu", "/usr/lib/x86_64-linux-gnu", "/usr/lib/python3.10/lib-dynload"):
            retain_system_notice(Path(prefix) / path.name)
        # Retain distro notices for every host shared library collected by
        # PyInstaller, including Tk's X11 libraries. Converter notices come
        # from its independently verified publish inputs.
        for name in re.findall(r"(?:=>\s*)?(/[^\s]+)", output):
            library = Path(name)
            if folder in library.parents or not library.is_file():
                continue
            retain_system_notice(library)
    if maximum_glibc > (2, 35):
        raise ValueError(f"Bundle needs glibc {maximum_glibc[0]}.{maximum_glibc[1]}, newer than the Ubuntu 22.04 build baseline")
    return dict(maximum_glibc=".".join(map(str, maximum_glibc)), elf_dependencies=dependencies)


ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<rect x="12" y="12" width="232" height="232" rx="44" fill="#172a43"/>
<rect x="47" y="47" width="162" height="162" rx="28" fill="#e1edf8" transform="rotate(-10 128 128)"/>
<g fill="#172a43"><circle cx="82" cy="82" r="14"/><circle cx="174" cy="82" r="14"/><circle cx="128" cy="128" r="14"/><circle cx="82" cy="174" r="14"/><circle cx="174" cy="174" r="14"/></g></svg>
'''


def assemble_appdir(bundle: Path, inputs: dict[str, Path], licenses: Path) -> tuple[Path, dict]:
    appdir = BUILD / "FFTIC-Randomizer.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    destination = appdir / "usr/bin"
    shutil.copytree(bundle, destination, symlinks=True)
    resources = destination / "_internal"
    for name, source in inputs.items():
        target = resources / name
        if not target.is_file() or digest(target) != digest(source):
            raise ValueError(f"Frozen resource differs from its verified input: {name}")
    converter = resources / CONVERTER_DESTINATION
    (converter / "FF16Tools.CLI").chmod(0o755)
    dependency_report = inspect_native_dependencies(destination, converter, licenses)
    shutil.copytree(licenses, resources / "licenses", dirs_exist_ok=True)
    (appdir / "AppRun").write_text('#!/bin/sh\nset -eu\napp_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$app_dir/usr/bin/FFTICRandomizer" "$@"\n', encoding="utf-8")
    (appdir / "AppRun").chmod(0o755)
    (appdir / "fftic-randomizer.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=FFTIC Randomizer\nComment=Generate randomizer seeds for FFTIC Enhanced\n"
        "Exec=AppRun\nIcon=fftic-randomizer\nTerminal=false\nCategories=Game;Utility;\n", encoding="utf-8")
    (appdir / "fftic-randomizer.svg").write_text(ICON_SVG, encoding="utf-8")
    shutil.copyfile(appdir / "fftic-randomizer.svg", appdir / ".DirIcon")
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.txt"):
        shutil.copyfile(ROOT / name, appdir / name)
    shutil.copytree(licenses, appdir / "licenses", dirs_exist_ok=True)
    (appdir / "docs").mkdir()
    for name in ("INSTALL.md", "SETTINGS.md", "LINUX.md"):
        source = ROOT / "docs" / name
        if source.is_file():
            shutil.copyfile(source, appdir / "docs" / name)
    (appdir / "README.txt").write_text(
        f"FFTIC Randomizer {VERSION} — native Linux x64\n\n"
        "Steam Deck: switch to Desktop Mode, extract this folder, and open AppRun.\n"
        "From a terminal: ./AppRun\n"
        "Python, Tk, FF16Tools and its runtime are included.\n"
        "Select the game folder containing FFT_enhanced.exe, choose a seed and settings,\n"
        "then click Generate randomizer mod. The game and Reloaded-II run through Proton.\n"
        "Read docs/LINUX.md for Steam Deck setup and docs/SETTINGS.md for each setting.\n\n"
        "Requires a Linux x64 desktop with glibc 2.35 or newer (Ubuntu 22.04 baseline).\n"
        "Use the AppImage's --appimage-extract-and-run option if FUSE is unavailable,\n"
        "or use this portable folder instead. No SteamOS system changes are required.\n"
        "This build is experimental until real Steam Deck gameplay validation completes.\n",
        encoding="utf-8")
    receipt = dict(generator_version=VERSION, python_version=sys.version.split()[0],
                   pyinstaller_version=PYINSTALLER_VERSION, platform="Linux x64", layout="AppDir-onedir",
                   build_baseline="Ubuntu 22.04", minimum_glibc="2.35", live_steam_deck_validation=False,
                   converter=json.loads((converter / "build-receipt.json").read_text(encoding="utf-8")),
                   sources={path.relative_to(ROOT).as_posix(): digest(path) for path in
                            [ROOT / "randomizer.py", ROOT / "tools/build_linux.py", *sorted((ROOT / "fftic").glob("*.py"))]},
                   resources={name: digest(path) for name, path in sorted(inputs.items())},
                   native_dependency_audit=dependency_report)
    write_json(appdir / "build-receipt.json", receipt)
    return appdir, receipt


def smoke_check(command: list[str], label: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="fftic-linux-smoke-") as temporary:
        environment = os.environ.copy()
        for name in ("DOTNET_ROOT", "DOTNET_ROOT_X64", "DOTNET_ROOT_X86", "FFTIC_FF16TOOLS", "PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH"):
            environment.pop(name, None)
        environment.update(FFTIC_DATA_DIR=str(Path(temporary) / "cache"), PATH="/usr/bin:/bin",
                           APPIMAGE_EXTRACT_AND_RUN="1", DOTNET_ROOT=str(Path(temporary) / "unavailable-dotnet"),
                           DOTNET_ROOT_X64=str(Path(temporary) / "unavailable-dotnet"), DOTNET_MULTILEVEL_LOOKUP="0")
        help_result = run([*command, "--help"], environment=environment, timeout=45)
        if "FFTIC Enhanced seeded table randomizer" not in help_result.stdout:
            raise ValueError(f"Frozen CLI help was unexpected: {label}")
        fixtures = ROOT / "research/linux-converter-build/fixtures"
        if not (fixtures / "131089-1.gdeflate").is_file():
            raise ValueError("Reference-compressed synthetic fixture missing for frozen converter smoke")
        integration_work = BUILD / f"{label}-converter-integration"
        smoke = run(["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", *command, "--bundle-smoke", str(fixtures), str(integration_work)],
                    environment=environment, log=BUILD / f"{label}-smoke.log", timeout=60)
        line = next((line for line in reversed(smoke.stdout.splitlines()) if line.startswith("{")), None)
        report = json.loads(line or "{}")
        if report.get("result") != "passed":
            raise ValueError(f"Frozen GUI/converter smoke did not pass: {label}")
        if set(report.get("converter_integration", {})) != {"specific_compressed_pac", "shared_compressed_pac", "nxd_sqlite_roundtrip", "globalization_probe"}:
            raise ValueError(f"Frozen converter did not complete synthetic PAC and Nex integration: {label}")
        probe = report["converter_integration"]["globalization_probe"]
        if (probe.get("result") != "passed" or probe.get("icu_version") != APP_LOCAL_ICU_VERSION
                or probe.get("invariant_mode") is not False or probe.get("icu_from_app_directory") is not True):
            raise ValueError(f"Frozen converter did not load its bundled ICU with full Unicode support: {label}")
        report.update(cli_help="passed", isolated_cache=True, global_dotnet_root_unavailable=True)
        write_json(BUILD / f"{label}-smoke.json", report)
        return report


def make_packages(appdir: Path, prepare: bool, smoke: bool) -> list[Path]:
    outputs = ROOT / "outputs"
    outputs.mkdir(exist_ok=True)
    tool_path = ROOT / "vendor/linux-packaging/appimagetool-1.9.1-x86_64.AppImage"
    runtime = ROOT / "vendor/linux-packaging/runtime-x86_64"
    if prepare:
        download(f"https://github.com/AppImage/appimagetool/releases/download/{APPIMAGETOOL_VERSION}/appimagetool-x86_64.AppImage", tool_path, APPIMAGETOOL_SHA256)
        download(APPIMAGE_RUNTIME_ASSET, runtime, APPIMAGE_RUNTIME_SHA256)
    for path, expected in ((tool_path, APPIMAGETOOL_SHA256), (runtime, APPIMAGE_RUNTIME_SHA256)):
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Pinned AppImage packaging dependency missing: {path}; use --prepare-dependencies")
    tool_path.chmod(0o755)
    appimage = outputs / f"FFTIC-Randomizer-{VERSION}-x86_64.AppImage"
    environment = os.environ.copy()
    environment.update(ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1", VERSION=VERSION)
    run([str(tool_path), "--runtime-file", str(runtime), str(appdir), str(appimage)],
        environment=environment, log=BUILD / "appimage-build.log", timeout=300)
    appimage.chmod(0o755)
    if smoke:
        smoke_check([str(appimage)], "appimage")
    archive = outputs / f"fftic-randomizer-{VERSION}-linux-x64.tar.gz"
    archive_root = f"FFTIC-Randomizer-{VERSION}-Linux-x64"
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
        bundle.add(appdir, arcname=archive_root)
    with tarfile.open(archive, "r:gz") as bundle:
        names = bundle.getnames()
        if f"{archive_root}/AppRun" not in names or any(".." in Path(name).parts or name.startswith("/") for name in names):
            raise ValueError("Portable archive manifest was invalid")
        if any(name.lower().endswith((".pac", ".nxd", ".sqlite", ".pdb")) for name in names):
            raise ValueError("Private game/cache input appeared in the portable archive")
    checksums = outputs / f"fftic-randomizer-{VERSION}-linux-x64-checksums.txt"
    checksums.write_text("".join(f"{digest(path)}  {path.name}\n" for path in (appimage, archive)), encoding="utf-8")
    receipt = outputs / f"fftic-randomizer-{VERSION}-linux-x64-build-receipt.json"
    report = json.loads((appdir / "build-receipt.json").read_text(encoding="utf-8"))
    report.update(appimagetool_version=APPIMAGETOOL_VERSION, appimagetool_sha256=APPIMAGETOOL_SHA256,
                  appimage_runtime_sha256=APPIMAGE_RUNTIME_SHA256,
                  artifacts={path.name: dict(sha256=digest(path), bytes=path.stat().st_size) for path in (appimage, archive)},
                  automated_smoke_checks=smoke)
    write_json(receipt, report)
    return [appimage, archive, checksums, receipt]


def test_no_system_icu() -> dict:
    """Run the actual release files without host ICU, Python, or .NET installed.

    The temporary X server runs on the build host. Its socket/auth cookie are
    mounted read-only, so the runtime container needs no graphics packages
    whose transitive dependencies might silently install ICU.
    """
    if shutil.which("docker") is None:
        raise ValueError("Docker is required for the isolated no-system-ICU release check")
    outputs = ROOT / "outputs"
    appimage = outputs / f"FFTIC-Randomizer-{VERSION}-x86_64.AppImage"
    archive = outputs / f"fftic-randomizer-{VERSION}-linux-x64.tar.gz"
    for path in (appimage, archive):
        if not path.is_file():
            raise ValueError(f"Build the release files before the isolated runtime check: {path.name}")
    fixtures = ROOT / "research/linux-converter-build/fixtures"
    if not (fixtures / "131089-1.gdeflate").is_file():
        raise ValueError("Reference-compressed fixture is missing for isolated runtime checks")
    context = BUILD / "no-system-icu"
    context.mkdir(parents=True, exist_ok=True)
    dockerfile = context / "Dockerfile"
    install = (
        "apt-get update\n"
        "apt-get install --no-install-recommends -y libssl3 libstdc++6 zlib1g fontconfig-config fonts-dejavu-core\n"
        "if dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\\n' 'libicu*' 2>/dev/null | grep -q '^ii'; then exit 1; fi\n"
        "if find /usr /lib -name 'libicu*.so*' -print -quit | grep -q .; then exit 1; fi\n"
    )
    dockerfile.write_text(f"FROM {NO_ICU_BASE_IMAGE}\nENV DEBIAN_FRONTEND=noninteractive\n"
                          + "RUN " + json.dumps(["sh", "-ec", install]) + "\n", encoding="utf-8")
    image = f"fftic-no-system-icu:{VERSION}"
    run(["docker", "build", "--pull", "--no-cache", "--tag", image, str(context)],
        log=context / "docker-build.log", timeout=600)
    image_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", image]).stdout.strip()
    control = context / "missing-icu-control"
    if control.exists():
        shutil.rmtree(control)
    shutil.copytree(BUILD / "converter", control)
    configuration = control / "FF16Tools.CLI.runtimeconfig.json"
    value = json.loads(configuration.read_text(encoding="utf-8"))
    value["runtimeOptions"]["configProperties"]["System.Globalization.AppLocalIcu"] = "0.0.0.0"
    value["runtimeOptions"]["configProperties"]["System.Globalization.Invariant"] = False
    write_json(configuration, value)
    (control / "FF16Tools.CLI").chmod(0o755)
    script = context / "check.sh"
    script.write_text(
        "#!/bin/sh\nset -eu\nulimit -c 0\n"
        "if command -v python3 >/dev/null 2>&1 || command -v dotnet >/dev/null 2>&1; then exit 1; fi\n"
        "if dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\\n' 'libicu*' 2>/dev/null | grep -q '^ii'; then exit 1; fi\n"
        "if find /usr /lib -name 'libicu*.so*' -print -quit | grep -q .; then exit 1; fi\n"
        "if ldconfig -p | grep -q libicu; then exit 1; fi\n"
        "printf 'No system ICU libraries, Python, or .NET executables are installed.\\n'\n"
        "export DOTNET_ROOT=/tmp/fftic-unavailable-dotnet\nexport DOTNET_ROOT_X64=$DOTNET_ROOT\n"
        "export DOTNET_MULTILEVEL_LOOKUP=0\nexport APPIMAGE_EXTRACT_AND_RUN=1\n"
        "export FFTIC_DATA_DIR=/tmp/fftic-no-icu-cache\n"
        "if /control/FF16Tools.CLI --fftic-globalization-probe > /evidence/missing-icu-control.log 2>&1; then\n"
        "  printf 'Missing app-local ICU control unexpectedly succeeded.\\n' >&2\n  exit 1\nfi\n"
        "grep -qi 'Failed to load app-local ICU' /evidence/missing-icu-control.log\n"
        "mkdir -p /tmp/fftic-portable\n"
        f"tar -xzf /release/{archive.name} -C /tmp/fftic-portable\n"
        f"/tmp/fftic-portable/FFTIC-Randomizer-{VERSION}-Linux-x64/AppRun --bundle-smoke /fixtures /evidence/portable-integration > /evidence/portable-smoke.log 2>&1\n"
        f"/release/{appimage.name} --bundle-smoke /fixtures /evidence/appimage-integration > /evidence/appimage-smoke.log 2>&1\n"
        "cat /evidence/portable-smoke.log\ncat /evidence/appimage-smoke.log\n", encoding="utf-8")
    evidence = context / "evidence"
    evidence.mkdir(exist_ok=True)
    launcher = context / "launch.sh"
    launcher.write_text(
        "#!/bin/sh\nset -eu\n"
        f"exec docker run --rm --network none --hostname {shlex.quote(socket.gethostname())} --env DISPLAY --env XAUTHORITY=/tmp/fftic-xauthority "
        f"--volume /tmp/.X11-unix:/tmp/.X11-unix:ro "
        f"--volume \"$XAUTHORITY:/tmp/fftic-xauthority:ro\" "
        f"--volume {shlex.quote(str(outputs) + ':/release:ro')} --volume {shlex.quote(str(fixtures) + ':/fixtures:ro')} "
        f"--volume {shlex.quote(str(control) + ':/control:ro')} --volume {shlex.quote(str(script) + ':/check.sh:ro')} "
        f"--volume {shlex.quote(str(evidence) + ':/evidence')} {shlex.quote(image)} sh /check.sh\n", encoding="utf-8")
    run(["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", "sh", str(launcher)],
        log=context / "container-runtime.log", timeout=180)
    reports = {}
    for name in ("portable", "appimage"):
        text = (evidence / f"{name}-smoke.log").read_text(encoding="utf-8")
        line = next((line for line in reversed(text.splitlines()) if line.startswith("{")), None)
        report = json.loads(line or "{}")
        if report.get("result") != "passed" or not report.get("converter_integration"):
            raise ValueError(f"Packaged {name} did not pass in the no-system-ICU container")
        probe = report["converter_integration"].get("globalization_probe", {})
        if (probe.get("result") != "passed" or probe.get("icu_version") != APP_LOCAL_ICU_VERSION
                or probe.get("invariant_mode") is not False or probe.get("icu_from_app_directory") is not True):
            raise ValueError(f"Packaged {name} did not prove bundled ICU in the isolated runtime")
        reports[name] = report
    result = dict(result="passed", base_image=NO_ICU_BASE_IMAGE, runtime_image_id=image_id,
                  system_icu_installed=False, system_python_installed=False, system_dotnet_installed=False,
                  missing_app_local_icu_control="failed as expected", packaged_runtime_checks=reports)
    write_json(context / "result.json", result)
    receipt_path = outputs / f"fftic-randomizer-{VERSION}-linux-x64-build-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["no_system_icu_runtime_check"] = result
    write_json(receipt_path, receipt)
    print("Portable archive and AppImage passed without system ICU, Python or .NET.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-dependencies", action="store_true", help="Build pinned converter and prepare pinned Python/AppImage packaging dependencies")
    parser.add_argument("--converter", type=Path, default=BUILD / "converter", help="Verified self-contained Linux converter publish directory")
    parser.add_argument("--check-only", action="store_true", help="Verify resource inputs without freezing or packaging")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip Xvfb GUI smoke for local diagnostic builds; release CI always runs it")
    parser.add_argument("--test-no-system-icu", action="store_true", help="Test already built release files in a fresh Docker container without system ICU/Python/.NET")
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise ValueError("Build on Linux x64; PyInstaller cannot cross-compile a Linux application from Windows")
    BUILD.mkdir(parents=True, exist_ok=True)
    if args.test_no_system_icu:
        test_no_system_icu()
        return 0
    if args.prepare_dependencies:
        run([sys.executable, str(ROOT / "tools/linux-converter/build.py"), "--output", str(args.converter)],
            log=BUILD / "converter-build.log", timeout=1800)
    python = build_python(args.prepare_dependencies)
    validate_native_receipt()
    licenses = collect_notices(python, args.converter, args.prepare_dependencies)
    inputs = collect_inputs(args.converter, licenses)
    write_json(BUILD / "bundle-inputs.json", {name: digest(path) for name, path in sorted(inputs.items())})
    print(f"Verified {len(inputs)} authored/converter resource inputs; game data is excluded.")
    if args.check_only:
        return 0
    spec = write_spec(inputs)
    run([str(python), "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(BUILD / "dist"),
         "--workpath", str(BUILD / "pyinstaller"), str(spec)], log=BUILD / "pyinstaller-build.log", timeout=900)
    appdir, _ = assemble_appdir(BUILD / "dist/FFTICRandomizer", inputs, licenses)
    if not args.skip_smoke:
        smoke_check([str(appdir / "AppRun")], "portable")
    for path in make_packages(appdir, args.prepare_dependencies, not args.skip_smoke):
        print(f"Built: {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
