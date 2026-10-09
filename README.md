# FFTIC Randomizer

A seeded randomizer for **Final Fantasy Tactics: The Ivalice Chronicles — Enhanced**,
on Windows x64. Change job abilities, equipment, monsters, encounters, rewards,
and more. Ordinary and unique jobs share the same settings, and shared job
changes apply throughout the game, including the opening battle.

## Download

Open the [Releases page](https://github.com/Pyre-Flies/FFTIC-Randomizer/releases/latest) and download
**fftic-randomizer-0.6.2-windows-x64.zip** from **Assets**. Extract the ZIP and
open **FFTIC Randomizer.exe**.

The app includes Python, FF16Tools, and the runtime it needs. You need your own
installed game, [Reloaded-II](https://github.com/Reloaded-Project/Reloaded-II/releases),
and [FFTIC Mod Loader 1.7.5 or newer](https://github.com/Nenkai/fftivc.utility.modloader/releases)
to play the generated mod.

**[Follow the installation and first-run guide](docs/INSTALL.md)** for complete setup.

## Quick start

1. Extract the Windows ZIP and open **FFTIC Randomizer.exe**.
2. Check **Game folder**. It must contain **FFT_enhanced.exe**.
3. Enter a seed, choose your settings, and click **Generate randomizer mod**.
4. Click **Open output**. Copy the entire **fftivc.randomizer.seed** folder into
   Reloaded-II's **Mods** folder, or drag **randomizer-mod.zip** onto Reloaded-II.
5. Enable the mod and FFTIC Mod Loader for Enhanced, then click
   **Launch Application** in Reloaded-II.

Use one active seed at a time. Close the game before replacing a seed and replace
the whole mod folder. A separate save slot is recommended because changing or
removing the mod does not undo character data already stored in a save.

## Choose your experience

- **Shuffle** exchanges abilities between existing job lists using the established
  rules. Some familiar abilities and special menus remain.
- **Full redistribution** rebuilds ability lists from separate humanoid and monster
  pools. Pools refill after exhaustion. Humanoid jobs receive reaction, support,
  and movement abilities by default.

Choose which parts of the game change and how much they vary. Hover over settings
for help, or focus them with Tab. The window resizes and scrolls on smaller screens.
**[Read the settings guide](docs/SETTINGS.md)** for both modes and every option.

## Your generated files

Seeds are saved to **Documents\FFTIC Randomizer\Seeds** by default. Each output
contains the installable mod, **job-abilities.txt**, **spoiler.txt**, and
**manifest.json**, which records the seed and settings. The app reads your
installed game and creates the mod separately from the original files.

This release supports the verified Enhanced build and checks it before generation.
Classic mode is not supported. Startup and loader checks have passed; a complete
campaign and every ability combination have not been playtested.

For a problem report, include the version, seed, settings or **manifest.json**,
the exact error, and a fresh Reloaded-II log. Troubleshooting is included in the
[first-run guide](docs/INSTALL.md#if-something-does-not-work).

## Credits

[Rumble Chaos Crashdown by abyssonym](https://github.com/abyssonym/rumble_chaos_crashdown)
provides the original randomization rules and built-in changes.
[FF16Tools by Nenkai](https://github.com/Nenkai/FF16Tools) provides archive extraction
and table conversion and is included in the Windows app.
[Nenkai's FFTIC Mod Loader](https://github.com/Nenkai/fftivc.utility.modloader),
[Nex layouts](https://github.com/Nenkai/fftivc-nex-layouts),
[Gibbed's tools](https://github.com/gibbed/Gibbed.IvaliceChronicles), and
[Reloaded-II](https://github.com/Reloaded-Project/Reloaded-II) provide the loading
and format tools behind the generated mod.

For source builds, see [Development](docs/DEVELOPMENT.md). Technical parity and
validation notes are in [docs/RCC-PARITY.md](docs/RCC-PARITY.md) and
[docs/RESEARCH.md](docs/RESEARCH.md).
