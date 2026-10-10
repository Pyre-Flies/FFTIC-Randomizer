# FFTIC Randomizer 0.6.3

This release adds a native Linux app, including Steam Deck Desktop Mode support.
Python, FF16Tools, and the converter's runtime are included. Steam libraries on
internal drives and SD cards are detected automatically, and output folders
follow your Linux desktop settings.

## Download

- **Linux / Steam Deck:** `FFTIC-Randomizer-0.6.3-x86_64.AppImage`. Make it executable and open it. If FUSE is unavailable, launch with `--appimage-extract-and-run`.
- **Portable Linux:** `fftic-randomizer-0.6.3-linux-x64.tar.gz`. Extract it and open `AppRun`.
- **Windows:** `fftic-randomizer-0.6.3-windows-x64.zip`. Extract it and open `FFTIC Randomizer.exe`.
- **Source:** `fftic-randomizer-0.6.3-source.zip`.

Read the [Linux and Steam Deck guide](https://github.com/Pyre-Flies/FFTIC-Randomizer/blob/v0.6.3/docs/LINUX.md),
[Windows setup guide](https://github.com/Pyre-Flies/FFTIC-Randomizer/blob/v0.6.3/docs/INSTALL.md),
and [settings guide](https://github.com/Pyre-Flies/FFTIC-Randomizer/blob/v0.6.3/docs/SETTINGS.md).

The Linux randomizer runs natively. Playing its generated mod still requires
FFTIC Enhanced, Reloaded-II, and FFTIC Mod Loader under Proton. Game loading on
an actual Steam Deck has not been verified and remains experimental.

The Linux package targets x86_64 with glibc 2.35 or newer. It is checked on
Ubuntu 22.04, including native codec and converter integration, portable source
tests, and frozen GUI startup. The Windows regression suite and a fresh
Reloaded-II launch are checked separately. A complete campaign has not been
playtested.

Use one active seed at a time. Close the game before replacing the whole mod
folder, and use a separate save slot.

Credits: [abyssonym's Rumble Chaos Crashdown](https://github.com/abyssonym/rumble_chaos_crashdown),
[Nenkai's FF16Tools](https://github.com/Nenkai/FF16Tools), FFTIC Mod Loader and Nex
layouts, Microsoft DirectStorage and NVIDIA libdeflate, Gibbed's tools, and
Reloaded-II. Full credits are available in **About / Credits**.
