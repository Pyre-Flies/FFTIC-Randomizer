# Install and play

FFTIC Randomizer 0.6.3 creates a mod for the **Enhanced version of Final Fantasy
Tactics: The Ivalice Chronicles on Windows x64**. You choose a seed and settings,
generate the mod, then play it through Reloaded-II.

For a native Linux app or Steam Deck setup, use the [Linux guide](LINUX.md).

The Windows download includes everything needed to run the randomizer. You do
not need to install Python or FF16Tools separately. You still need your own
installed game, Reloaded-II, and the FFTIC Mod Loader.

## 1. Download the randomizer

1. Open the [FFTIC Randomizer Releases page](https://github.com/Pyre-Flies/FFTIC-Randomizer/releases/latest).
2. Under **Assets**, download **fftic-randomizer-0.6.3-windows-x64.zip**.
   The source download is for development; choose the Windows ZIP to play.
3. Right-click the ZIP and choose **Extract All**. Extract it to a folder of
   your choice, such as `Documents\FFTIC Randomizer App`, outside the game folder.
4. Open **FFTIC Randomizer.exe** from the extracted folder.

Keep the extracted package together. The randomizer checks that your game build
is supported before generating a mod. Classic mode is not supported by this
release.

## 2. Set up Reloaded-II once

If you already use Reloaded-II with FFTIC Mod Loader 1.7.5 or newer, skip to
[generating a seed](#3-generate-a-seed).

1. Download **Setup.exe** from the official
   [Reloaded-II releases](https://github.com/Reloaded-Project/Reloaded-II/releases)
   and run it. Alternatively, extract its `Release.zip` to its own folder.
2. Open **Reloaded-II.exe**. Click **+** to add a game, then select
   **FFT_enhanced.exe** in your game folder. To find that folder in Steam,
   right-click the game and choose **Manage → Browse local files**.
3. Add **FFT_classic.exe** as a second application so switching game modes can
   work. Use **Edit Application** to give the entries distinct Enhanced and
   Classic names. Play the randomizer from the Enhanced entry.
4. Download **fftivc.utility.modloader.7z**, version **1.7.5 or newer**, from
   [FFTIC Mod Loader releases](https://github.com/Nenkai/fftivc.utility.modloader/releases).
5. Drag that archive onto Reloaded-II. In the Enhanced application's mod list,
   enable **FINAL FANTASY TACTICS - The Ivalice Chronicles Mod Loader** and any
   dependencies Reloaded-II requests.

These steps follow [Nenkai's FFTIC setup guide](https://nenkai.github.io/ffxvi-modding/modding/installing_mods_fft/).
For launcher help, see the [Reloaded-II quick start](https://reloaded-project.github.io/Reloaded-II/QuickStart/).

## 3. Generate a seed

1. In **FFTIC Randomizer.exe**, check **Game folder**. It should be the folder
   containing **FFT_enhanced.exe**. The app searches Steam libraries automatically;
   use **Browse** if it selects the wrong folder.
2. Choose **Output folder**, or keep the default:
   `Documents\FFTIC Randomizer\Seeds`. Windows' Documents location is used,
   including a redirected OneDrive Documents folder.
3. Keep the suggested **Seed**, type your own text, or click **New seed**.
   The same seed, settings, app version, and supported game build reproduce the
   same result.
4. Choose your settings. **Shuffle** is the default. For completely rebuilt job
   skillsets, choose **Full redistribution**. See [Settings](SETTINGS.md) for
   the differences and each option's description.
5. Click **Generate randomizer mod** and wait for the completion message.
   The first generation needs time to read and prepare your installed game data.
6. Click **Open output**. This opens the completed seed folder.

Hover over settings for help, or reach them with the Tab key. On a small screen,
resize the window or scroll the settings; the buttons stay at the bottom.

The app creates the mod separately from the original game files. It stores
reusable caches in `%LOCALAPPDATA%\FFTIC Randomizer`. Folder choices and settings
are not saved between app launches in this version.

## 4. Install the generated mod

Close the game before installing or changing a seed.

In the output you just opened, find **fftivc.randomizer.seed**. Copy that whole
folder into Reloaded-II's **Mods** folder. For example, if Reloaded-II is installed
at `C:\Reloaded-II`, the result should be:

```text
C:\Reloaded-II\Mods\fftivc.randomizer.seed\ModConfig.json
```

`ModConfig.json` must sit directly inside the mod folder. Do not copy only that
file, and do not add an extra `seed-...` folder between **Mods** and
**fftivc.randomizer.seed**. All of the generated folder's files belong together.

You can instead drag the generated **randomizer-mod.zip** onto Reloaded-II.
The ZIP contains the same installable mod folder. Manual folder installation
follows the [Reloaded-II installation instructions](https://reloaded-project.github.io/Reloaded-II/FAQ/#how-can-i-install-mods-manually).

Restart Reloaded-II if the new mod does not appear. Select the Enhanced application
and enable both **FFTIC Randomizer – your seed** and **FFTIC Mod Loader**. If the
randomizer is missing from that application's list, open **Manage Mods**, select
it, and assign it to Enhanced. [Reloaded-II mod selection help](https://reloaded-project.github.io/Reloaded-II/QuickStart/)

## 5. Launch and play

Select Enhanced in Reloaded-II and click **Launch Application**. Keep Steam
running if your game needs it. Generate and install only one active seed at a time.

No downloaded save or special test save is required to start. A new game with a
separate save slot is recommended: job and encounter changes also apply in the
opening battle. Existing saves contain stored character data that may not
recalculate when you change seeds. Startup validation has been performed, but
every battle and a complete campaign have not been playtested.

For a preview before playing, open **job-abilities.txt** in the seed output.
**spoiler.txt** lists broader changes. **manifest.json** records the seed and
settings so you can share or reproduce them.

## Change a seed or remove the randomizer

To change seeds, close the game, move the old installed
**fftivc.randomizer.seed** folder somewhere outside **Mods** as a backup, and copy
the entire new folder into **Mods**. Replace the folder rather than merging files.
Enable the new seed in Reloaded-II and relaunch Enhanced.

To stop using the randomizer, close the game, disable it in Reloaded-II, and
relaunch. The loader's table, event, and runtime changes are removed on restart;
changes already stored in a save are not undone. Keep separate randomized and
ordinary saves.

## If something does not work

| Problem | What to check |
| --- | --- |
| Game folder is wrong | Browse to the folder containing `FFT_enhanced.exe`, not its `data` folder. |
| Unsupported build message | This release supports one verified Enhanced build. Include the message when reporting the issue. |
| Drag and drop does nothing | Restart Reloaded-II normally; Windows can block dragging files into a program running as administrator. Manual folder copying also works. |
| Randomizer missing from Reloaded-II | Check the folder layout above, restart Reloaded-II, and assign the mod through **Manage Mods**. |
| Game looks unchanged | Enable the loader and randomizer, then launch **Enhanced** with **Launch Application**. Check `job-abilities.txt`; Shuffle deliberately retains some familiar skillsets. |
| Error during launch | Check that the loader is version 1.7.5 or newer. Try with other gameplay mods disabled to identify conflicts. |
| Need to report a problem | Include the app version, seed, settings or `manifest.json`, exact error text, fresh Reloaded-II log, and `runtime-patches.log` from the installed seed folder. |
