# FFTIC Randomizer 0.6.4

This fixes seed generation on Steam Deck and Linux systems without ICU installed.
The Linux download now carries its own ICU libraries alongside FF16Tools and
.NET. Full Unicode and language support are retained. You do not need to unlock
SteamOS or install system packages to resolve the missing ICU error.

## Download

- **Linux / Steam Deck:** `FFTIC-Randomizer-0.6.4-x86_64.AppImage`. Make it executable and open it. If FUSE is unavailable, use `--appimage-extract-and-run`.
- **Portable Linux:** `fftic-randomizer-0.6.4-linux-x64.tar.gz`. Extract the whole archive and open `AppRun`.
- **Windows:** `fftic-randomizer-0.6.4-windows-x64.zip`. Extract it and open `FFTIC Randomizer.exe`.
- **Source:** `fftic-randomizer-0.6.4-source.zip`.

[Linux / Steam Deck setup](https://github.com/Pyre-Flies/FFTIC-Randomizer/blob/v0.6.4/docs/LINUX.md) ·
[Windows setup](https://github.com/Pyre-Flies/FFTIC-Randomizer/blob/v0.6.4/docs/INSTALL.md) ·
[Settings](https://github.com/Pyre-Flies/FFTIC-Randomizer/blob/v0.6.4/docs/SETTINGS.md)

Both Linux downloads are checked in a clean Linux environment without system
ICU, Python or .NET. The checks cover the bundled ICU being loaded, culture and
Unicode behavior, compressed extraction, exact table conversion and GUI startup.
The randomization rules are unchanged.

The Linux app targets x86_64 with glibc 2.35 or newer. Playing the generated mod
still requires FFTIC Enhanced, Reloaded-II and FFTIC Mod Loader under Proton.
Actual Steam Deck gameplay remains experimental and has not been verified.

Credits: [abyssonym's Rumble Chaos Crashdown](https://github.com/abyssonym/rumble_chaos_crashdown),
[Nenkai's FF16Tools](https://github.com/Nenkai/FF16Tools), FFTIC Mod Loader and Nex
layouts, Microsoft DirectStorage and ICU, NVIDIA libdeflate, Gibbed's tools,
and Reloaded-II. Full credits are available in **About / Credits**.
