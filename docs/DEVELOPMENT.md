# Build from source

Use the Windows ZIP or Linux AppImage to play. These steps are for changing or rebuilding the app.
The source ZIP includes the generator, authored resources, runtime sources,
runtime DLLs, and their build receipts.

## Run the generator

Use Windows x64 and Python 3.10 or newer. The release uses Python 3.13.13.
Extract the official [FF16Tools CLI 1.13.3 Windows x64 download](https://github.com/Nenkai/FF16Tools/releases/tag/1.13.3)
so its executable is at `vendor/FF16Tools-1.13.3/win-x64/FF16Tools.CLI.exe`, or
set `FFTIC_FF16TOOLS` to that executable. Keep its layouts alongside it.

From the source folder:

```powershell
python randomizer.py gui
python randomizer.py generate --seed example --ability-mode shuffle
python randomizer.py generate --seed example --ability-mode full
```

Source launches default to the source folder's parent as the game folder and
`outputs` as the output folder. Packaged apps search Steam libraries. Choose your installed game in the GUI, or use
`python randomizer.py generate --help` for command-line paths and settings.

## Build the Windows executable

Use 64-bit Windows Python. From the source folder:

```powershell
python tools/build_executable.py --prepare-dependencies
```

The script prepares an isolated build environment, downloads the pinned tools
and runtime, verifies their hashes, and creates the executable and Windows ZIP
under `outputs`. Later builds can omit `--prepare-dependencies`. Use
`--check-only` to verify inputs without rebuilding.

The source ZIP includes the prebuilt runtime DLLs. The build verifies their
source and binary hashes before bundling them. Native source changes require
rebuilding the DLLs and refreshing their receipt.

## Rebuild the native components

Install Visual Studio's MSVC x64 C++ tools, PowerShell 7 with bundled Roslyn, and
.NET 9 runtime metadata. You also need `Reloaded.Mod.Interfaces.dll` from your
Reloaded-II installation. From the source folder:

```powershell
pwsh -File tools/rebuild_runtime.ps1 -ReloadedSdkPath C:\Reloaded-II\Reloaded.Mod.Interfaces.dll
```

Use your actual SDK path if Reloaded-II is installed elsewhere. The script
builds both DLLs into `native/runtime` and refreshes their source/binary receipt.
See [AGENTS.md](../AGENTS.md) for the checks required after major changes.

## Build the native Linux app

Use Linux x86_64 with Python 3.10 or newer, Tk, Git, CMake, a C/C++ compiler,
patchelf, squashfs-tools, Xvfb, and .NET SDK **9.0.318**. The release workflow
uses Ubuntu 22.04 as its glibc 2.35 baseline. From the source folder:

```sh
python3 tools/build_linux.py --prepare-dependencies
```

This builds the pinned FF16Tools converter with a native CPU GDeflate decoder,
bundles its .NET runtime and Python/Tk, and creates an AppImage and portable
archive under `outputs`. The generated mod still contains Windows runtime DLLs
for FFTIC running through Proton. It does not need Wine to generate a seed.

The build runs codec fixtures, archive/table conversion checks, dependency and
hash checks, and frozen GUI startup under Xvfb. It excludes game archives and
local caches from the packages. The manual GitHub workflow in
`.github/workflows/linux-build.yml` runs these same steps and provides build
logs as an artifact. See [the converter build notes](../tools/linux-converter/README.md)
for its pinned inputs and extraction-only adapter.

Some parity tests and import tools expect a separate RCC reference checkout.
Inspect their path options before running them; that checkout is not needed
to run the Windows app. Dependencies, game archives, saves, local research
evidence, caches, and seed outputs are excluded from source packaging.
