# Linux and Steam Deck

The Linux download runs the randomizer natively. It includes Python, the archive
converter, and the converter's runtime. You do not need to install those or
change SteamOS's system packages to generate a seed.

The generated mod runs in the Windows version of FFTIC Enhanced under Proton,
using Reloaded-II and FFTIC Mod Loader. Linux generation and game loading are
separate steps. Steam Deck gameplay support is experimental until a real Deck
launch has been verified.

## Download and open the randomizer

1. On Steam Deck, switch to **Desktop Mode** from the Steam power menu.
2. Open the [Releases page](https://github.com/Pyre-Flies/FFTIC-Randomizer/releases/latest).
3. Download the **x86_64 AppImage**. Steam Deck uses this architecture.
4. Right-click the file, open **Properties → Permissions**, and allow it to run
   as a program. On other desktops this may be called **Executable**.
5. Open the AppImage. If your desktop asks how to open it, choose **Execute**.

For a terminal launch, use the actual downloaded filename:

```sh
chmod +x FFTIC-Randomizer-0.6.3-x86_64.AppImage
./FFTIC-Randomizer-0.6.3-x86_64.AppImage
```

If the AppImage reports that FUSE is unavailable, run it without mounting:

```sh
./FFTIC-Randomizer-0.6.3-x86_64.AppImage --appimage-extract-and-run
```

A portable Linux archive is also provided for systems where AppImage execution
is restricted. Extract the whole archive and keep its files together; use the
launcher in the extracted folder. The release downloads include a README with
the exact launcher name.

## Generate a seed

1. Check **Game folder**. The app searches native and Flatpak Steam libraries,
   including additional libraries such as an SD card.
2. If needed, browse to the installed game folder containing **FFT_enhanced.exe**.
   In Steam, **Manage → Browse local files** shows the right folder.
3. Choose a seed and settings. Read [Settings](SETTINGS.md) for the two ability modes.
4. Click **Generate randomizer mod**, then **Open output** when it finishes.

By default, seeds go into **Documents/FFTIC Randomizer/Seeds**, respecting your
desktop's configured Documents folder. Reusable extraction caches go into
**~/.cache/fftic-randomizer**, or your configured **XDG_CACHE_HOME**.

The app does not save folder selections and settings between launches. It checks
the supported Enhanced build before generating. The Classic version is not
supported.

## Set up the game under Proton

Use the current [Reloaded-II Linux setup guide](https://reloaded-project.github.io/Reloaded-II/LinuxSetupGuideNew/).
Its installer sets up the Windows loader inside the game's Proton environment.
You should run FFTIC through Steam once before doing this setup.

1. Install **Protontricks** using the method in that guide. On Steam Deck,
   Discover provides the Flatpak version.
2. Download **Setup-Linux.exe** from the official
   [Reloaded-II releases](https://github.com/Reloaded-Project/Reloaded-II/releases).
3. Open it with **Protontricks Launcher** and select **Final Fantasy Tactics:
   The Ivalice Chronicles**. Select the game's environment rather than a separate
   environment created for the native randomizer.
4. Open Reloaded-II using Protontricks as described in the guide. Add
   **FFT_enhanced.exe** from your game folder. Add **FFT_classic.exe** as well if
   you want the game's mode switching to work; launch the randomized game as Enhanced.
5. Install [FFTIC Mod Loader 1.7.5 or newer](https://github.com/Nenkai/fftivc.utility.modloader/releases)
   and enable it for Enhanced. The
   [FFTIC setup guide](https://nenkai.github.io/ffxvi-modding/modding/installing_mods_fft/)
   shows the game and loader selection.

## Install and play the generated mod

Close the game before changing seeds. Drag **randomizer-mod.zip** from the
generated output onto Reloaded-II, or copy the whole **fftivc.randomizer.seed**
folder into that Reloaded-II installation's **Mods** folder.

The correct layout ends with:

```text
Reloaded-II/Mods/fftivc.randomizer.seed/ModConfig.json
```

Do not insert an extra `seed-...` directory. Enable the randomizer and FFTIC Mod
Loader for Enhanced, then use **Launch Application** in Reloaded-II.

To launch directly from Steam afterward, follow the optional ASI-loader section
of Reloaded-II's Linux guide. Use the DLL override matching the loader file it
actually deploys. Avoid copying an unrelated game's launch options.

Use one active seed and a separate save slot. Replacing a seed means replacing
the entire installed mod folder while the game is closed. Disabling the mod and
restarting removes its runtime changes, but does not undo data stored in a save.

## Report a problem

Include the release version, Linux distro or SteamOS version, seed and settings,
exact error text, and the relevant converter or Reloaded-II log. For game-loading
problems also include **runtime-patches.log** from the installed mod folder and
the Proton version selected in Steam.

If the game is unchanged, confirm that you launched Enhanced with both mods
enabled. If generation fails, the game loader is not involved yet; include the
generator's error and conversion log.
