# Build from source

Use the Windows ZIP to play. These steps are for changing or rebuilding the app.
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
`outputs` as the output folder. Choose your installed game in the GUI, or use
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

Some parity tests and import tools expect a separate RCC reference checkout.
Inspect their path options before running them; that checkout is not needed
to run the Windows app. Dependencies, game archives, saves, local research
evidence, caches, and seed outputs are excluded from source packaging.
