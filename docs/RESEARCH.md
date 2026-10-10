# FFTIC research ledger — 2026-10-09

## Verified inputs

Workspace: the installed Steam game and the local `I:/rumble_chaos_crashdown` and
`I:/FF16Tools` checkouts. Original game executables and PAC archives are input
only. No runtime hooks or direct executable patches were installed.

| Input | Identity |
| --- | --- |
| RCC checkout | `ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`, version 27, Python 2.7/PS1 ISO |
| FF16Tools checkout | `14361aefa1e1265096b42cad95cd9f01550a0457` |
| FFTIC Nex layouts submodule | `d4a60952531d82bfd8a4fbb76b1f9b363f721dc1` |
| Inspected FFTIC loader source | `c74047dc1b36bfe1bf6a466cf3645f1fe9815425`; metadata version 1.7.5 |
| Downloaded CLI release | [FF16Tools 1.13.3](https://github.com/Nenkai/FF16Tools/releases/tag/1.13.3) |
| CLI ZIP SHA-256 | `9d653d95e2da9770fbbf12431bbcface876d209d1824925a08941aa87eee05e3` |
| Enhanced EXE SHA-256 | `937233f7fe76182a665c487c8802f5cec6662ddd09967e87cd09fb146fc6b5d5` |
| Classic EXE SHA-256 | `7cfcd294830b315248114c42f14ac7b1a2f35ba835c0cef8314d480601d15a9f` |

The CLI executable's console banner says 1.13.0 despite being in the official
1.13.3 release ZIP. Record the release artifact identity instead of trusting
that banner. A .NET 9 runtime is installed; no .NET SDK was available, so the
official CLI binary was used instead of building the checkout.

Primary schema/signature sources under the inspected loader:

- `fftivc.utility.modloader/Signatures/ffto.ini` and `ffto_denuvo.ini`.
- `fftivc.utility.modloader.Interfaces/Tables/Structures/*.cs`.
- `fftivc.utility.modloader.Interfaces/Tables/Models/*.cs`.
- `fftivc.utility.modloader/Tables/FFTO*DataManager.cs`.
- `fftivc.utility.modloader/TableData/*.xml`.

These signatures and field definitions were already discovered upstream. The
new local findings are their unique matches, translated RVAs, baseline hashes,
and validation against this installed executable. Do not attribute upstream
reverse engineering to this project.

## Enhanced tables: unique matches and mapped RVAs

Each upstream signature matched exactly once in the current on-disk executable.
An RVA is relative to the loaded module base, **not an absolute runtime address**.
File offsets and RVAs are different and must not be interchanged.

| Table | File offset of table start | RVA | Stride | Rows | Section |
| --- | --- | --- | --- | --- | --- |
| JobData | `0x784230` | `0x785E30` | 49 | 174 | `.data` |
| JobCommandData | `0x67D210` | `0x67E210` | 25 | 176 | `.rdata` |
| ItemData | `0x80CE90` | `0x80EA90` | 12 | 256 | `.data` |
| ItemWeaponData | `0x80DA90` | `0x80F690` | 8 | 128 | `.data` |
| ItemShieldData | `0x80DE90` | `0x80FA90` | 2 | 16 | `.data` |
| ItemArmorData | `0x80DEB0` | `0x80FAB0` | 2 | 64 | `.data` |
| ItemAccessoryData | `0x80DF30` | `0x80FB30` | 2 | 32 | `.data` |
| JobCommandDataWOTL | `0x67E340` | `0x67F340` | 25 | 3 | `.rdata` |
| MonsterJobCommandData | `0x67E4C0` | `0x67F4C0` | 5 | 48 | `.rdata` |
| CommandTypeData | `0x67D010` | `0x67E010` | 1 | 256 | `.rdata` |
| AbilityMetadata | `0x786380` | `0x787F80` | 8 | 512 | `.data` |

The complete discovered locations, block hashes, stride/count, and executable
hash are in `research/enhanced/build.json` and every generated `manifest.json`.
The executable guard and source signatures are also retained in `fftic/game.py`.

Anchoring details that prevent off-by-one table errors:

- Job signature matches **row 1** at file offset `0x784261`; subtract **49 bytes**.
- JobCommand signature matches **row 5** at `0x67D28D`; subtract **125 bytes**.
- Accessory signature matches **row 16** at `0x80DF50`; subtract **32 bytes**.
- Other supported signatures anchor the first table row directly.

## Packed fields used

All structures have pack=1 in the loader source; the PS1 JobData stride of 48 is
wrong for this executable. FFTIC has **five equipment-flag bytes**, producing
the verified stride of 49.

JobData offsets: command at `+0`; four ushort innate abilities at `+1..8`;
equipment flags at `+9..13`; HP growth/multiplier at `+14/15`; MP at `+16/17`;
speed at `+18/19`; PA at `+20/21`; MA at `+22/23`; move/jump/evasion at `+24/25/26`.
Status/element/monster fields beyond this region are not edited by the prototype.

JobCommandData offsets: action extension bits at `+0/1`, RSM extension byte at
`+2`, 16 action ID bytes at `+3..18`, 6 RSM bytes at `+19..24`. Extension bits run
**from bit 7 down to bit 0 within each byte**; an extended slot adds 256. They
are not a straightforward ascending-bit ushort mask. A unit test covers this.

The XML model's ability setters recalculate extension bits, but both nullable
extension fields must be initialized first; see the 0.1.1 correction below.
Patches therefore
include every action/RSM ID in each changed command row, including unchanged
IDs, to preserve bits belonging to untouched slots. The loader compares actual
values and tracks only differences. Writing only changed slots risks clearing
bits for other extended IDs.

ItemData: flags at `+3`, secondary row ID at `+4`, item category at `+5`, little
endian ushort price at `+8`, shop timing byte at `+10`. Low flag bits 0/1 mean
steal/break protection and rare status; the prototype excludes both. Equipment
flags: weapon `0x80`, shield `0x40`, head/body `0x30`, accessory `0x08`.

WeaponData power/evasion at `+4/5`. ArmorData HP/MP bonus at `+0/1`. ShieldData
and AccessoryData physical/magical evasion at `+0/1`. Secondary rows can be shared:
checking just the current item is insufficient to protect another item using
the same row. The generator excludes rows referenced by any protected item.

## IDs and separation of core data from Nex

Verified ordinary job IDs are **74–93**, with corresponding command IDs **5–24**.
Story jobs using a similar name have distinct IDs and are not included.
Mage commands selected for spell redistribution: 10 White Magicks, 11 Black
Magicks, 12 Time Magicks, 13 Summon, 16 Mystic Arts.

`AbilityData.xml` explicitly states that its `JPCost` field is unused; the game
uses the Ability Nex table's cost. `AbilityActionData.xml` is explicitly a
nonfunctional reminder pointing to `OverrideAbilityActionData.nxd`. Generating
either of these as if they controlled cost/CT/MP would produce a misleading mod.
They are not emitted by this prototype.

The loader also exposes job requirements, monster commands, spawns, and other
tables. The existence of an XML sample is not evidence that unrestricted random
values are safe. Requirements need reachable job trees; encounter units need
story/script protections, equipment legality, and usable positions.

## Archive work with FF16Tools

The initial guess that Enhanced `0001.pac` contained tables was incorrect.
Its internal archive directory is `char`, with four small TGA files. The next
archives were verified rather than reusing FFXVI archive-number assumptions:

- `data/enhanced/0004.pac`: nonlocalized `nxd/` files, including overrides.
- `data/enhanced/0004.en.pac`: English localized tables, including Job, Ability,
  JobCommand, Item, and text/PZD files.
- Extracted paths: `research/enhanced/0004/nxd/` and `0004.en/nxd/`.
- English SQLite conversion: `research/enhanced/tables.en.sqlite`.
- Tables are named `Job-en`, `JobCommand-en`, `Ability-en`, `Item-en` in SQLite;
  the primary column is `Key`, not `Id`. Filename spelling differs from SQL names.
- Counts: Job 174, JobCommand 227, Ability 512, Item 261.
- Private name-only lookup: `research/names.json` improves spoiler reports.

Commands used, from the project folder:

```powershell
$cli = 'vendor/FF16Tools-1.13.3/win-x64/FF16Tools.CLI.exe'
& $cli unpack-all -i '../data/enhanced/0004.pac' -o research/enhanced/0004 -g fft
& $cli unpack-all -i '../data/enhanced/0004.en.pac' -o research/enhanced/0004.en -g fft
& $cli nxd-to-sqlite -i research/enhanced/0004.en/nxd -o research/enhanced/tables.en.sqlite -g fft
```

Conversion reported all 53 English tables exported without errors.
`list-files` writes `<pack>_files.txt` beside its input, with no output argument;
the generated `0001_files.txt` was moved into research afterward.

## Classic observations — unsupported

The current Classic executable had unique raw signature matches at: ItemData
`0x663040`, WeaponData `0x663C40`, ShieldData `0x664040`, ArmorData `0x664060`,
Accessory **anchor** `0x664100`, JobCommand **anchor** `0x5363CD`.
The Enhanced JobData signature did **not** match. These are raw observations,
not fully validated Classic table-start addresses or runtime support. No Classic
randomizer package is generated. Revalidate the Classic job layout independently.

## Validation and remaining uncertainty

7,300 numeric fields matched the upstream sample XMLs with zero differences:
Job 2,436; JobCommand 3,872; Item 512; Weapon 256; Armor 128; Shield 32; Accessory
64. Enum-valued fields were not counted in that comparison. It confirms the
readers for the fields compared, not game loading or complete campaign behavior.

Initial 0.1.0 validation: eleven tests passed, with 40 seed/spread combinations checked for invariants.
The sample `ivalice-2026` / `jspw` / 25% seed produces 653 edited properties.
No live loader/game session was run at that initial stage; the 0.1.1 launch
below supersedes that startup-validation status. A hidden Tk smoke test constructed the
desktop interface successfully; its requested content size of 495×531 fits
inside the 740×630 window. Invoking its Generate button with seed `gui-smoke`
completed and produced 654 edited properties in a temporary output folder.
That check does not replace visual or game testing.

The user-supplied [Hacktics wiki](https://ffhacktics.com/wiki/FFT/TIC/Data_Tables)
returned HTTP 403 both through browsing and direct HTTP. The upstream loader
source and local executable/table comparisons supplied the verified evidence.

Existing `wininet.dll`, `scripts/FFTacticsFix.asi`, and both mode folders'
`modded.pac` files were present at initial inspection. They were not changed or
deleted. Their contents/interaction with a future live test remain unverified.

## 0.1.1 correction and real-loader launch — 2026-10-09

The user's first live run exposed `YAXPropertyCannotBeAssignedTo` for
`AbilityId1`. The source model has nullable `ExtendAbilityIdFlagBits` and
`ExtendReactionSupportMovementIdFlagBits`, with no default values. Every ability
setter dereferences the corresponding field's `.Value`. Omitting both XML nodes
was therefore a generator bug; automatic bit updates do not initialize nulls.

Corrected rows emit both fields as `0` before any action/RSM IDs. Complete ID
vectors then recalculate every extension bit through the existing setters.
All active seed IDs and randomized numeric values were preserved. A validation
process loaded the installed assemblies and reproduced the exact original error,
then successfully deserialized every corrected table. The regression test
removes the initialization nodes and expects the same failure. It also verifies
all numeric values, extended bits, and that omitted nullable properties stay null.

Installed loader version: **1.7.5**. Exact managed assembly SHA-256:

- Interfaces: `87abfdc07a8c6924acd7f2021951fcd3055d7a0d2212ad8fee49fa414f301e46`.
- Serializers: `38a6bad6030dec78c12a3809f18e2eade3036a3f1ac130056632d1e55e46fbaa`.

Runtime launch used `C:/Reloaded-II/Reloaded-II.exe --launch` with the registered
Enhanced executable. Existing application configuration enabled exactly the
FFTIC loader and `fftivc.randomizer.seed`, plus their required libraries.

User seed: `89f597b5`, flags `jspw`, spread 50%. Installed mod repaired at
`C:/Reloaded-II/Mods/fftivc.randomizer.seed/`; only JobCommandData XML and the
ModVersion metadata changed. A full pre-repair copy is at
`research/backups/installed-seed-before-0.1.1-20261009T123910Z/`.

Fresh log: `2026-10-09 12.39.11 ~ FFT_enhanced.txt`, under
`%APPDATA%/Reloaded-Mod-Loader-II/Logs/`. The local saved copy
is `research/live-validation/reloaded-fixed-seed.log` with structured audit at
`result.json` and serializer results at `serializer-result.json`.

Successful live table applications: ItemData 168; ItemWeaponData 136;
ItemShieldData 15; ItemArmorData 60; ItemAccessoryData 12; JobCommandData 60;
JobData 238. These are the loader's diff counts, not the generator's baseline
change count (689). Do not use them interchangeably.

No deserialization exception, load error, or mod conflict appeared. Total loader
initialization: 586 ms. Process remained responsive for 149 seconds and closed
normally through `CloseMainWindow`. No game input, save loading, battle, or
campaign test was performed.

The log includes an existing warning: `Pattern CFILE_DAT__Decode not found!`,
followed by a successful `CFILE_DAT__DecodeAlt` scan. The same warning occurs in
the pre-repair log. `Hooks/G2DHooks.cs` registers both variants to populate the
same DecodeHook. The primary-pattern warning does not mean that the alternative
hook failed. The full log is therefore not literally warning-free; the
randomizer's load error is resolved.

Observed module base was `0x7FF71F4E0000` for this launch only (ASLR). The live
JobData anchor `0x7FF71FC65E61` resolves to RVA `0x785E61`; subtract row stride
49 to recover table RVA `0x785E30`. JobCommand anchor `0x7FF71FB5E28D` resolves
to RVA `0x67E28D`; subtract five rows to recover `0x67E210`. Both corroborate the
earlier static mapping. Addresses in this launch log must not be reused as fixed
absolute addresses.

User requirement: before delivering future randomizer changes, run the actual
Reloaded-II loader and review a fresh log. Offline serialization is an additional
check, not a substitute. This requirement is retained in project `AGENTS.md`.

## Complete job/ability catalog and global allocation — 0.3.0

The initial JobData count of 176 followed the upstream manager's declared count.
This executable contains **174 real 49-byte rows**, ending at raw `0x78637E`,
followed by two alignment bytes and AbilityMetadata at `0x786380`. Reading or
editing the two extra rows would overlap ability data. The generator now stops
at 174 and identifies 147 active rows with nonzero job command and stats.

Additional uniquely matched tables are in the updated table above and seed
manifests. Base human commands are 0–175. WOTL-layout rows map to command IDs
224–226; most WOTL-specific action IDs are unused in this game's English data.
Monster commands are 176–223, four ID bytes with reverse extension bits 7–4.
Human commands retain the reverse per-byte extension layout documented above.
CommandTypeData is read for 256 IDs; no larger range is needed by these jobs.

AbilityMetadata uses upstream ABILITY_COMMON_DATA: ushort JP, byte learn chance,
byte flags, uint AI flags. The **low nibble** of flags is AbilityType, and the
**high nibble** is AbilityFlags. Types: 1 direct actions; 2 items; 3 throws;
4 jump; 5 aim; 6 math; 7 reaction; 8 support; 9 movement. These are native
dispatch categories, not spell schools. Direct actions include physical,
unique, monster and boss actions as well as spells.

At inspected loader source FFTOAbilityDataManager.cs lines 101–102,
ApplyTablePatch recomposes both nibbles from AbilityFlags, ignoring AbilityType.
For example, display-name flag 4 would also write low-nibble type 4. This is an
upstream source observation; it was not tested by emitting a corrupting patch.
The randomizer reads metadata only and emits no AbilityData XML.

Names, descriptions and actual JP costs come from original enhanced
`0004.en.pac`, internal `nxd/ability.en.nxd`, converted with the official CLI.
JP is encoded as **JpCost1 | (JpCost2 << 8)**. Do not treat the second byte as a
second independent cost. The full catalog combines all 512 native IDs with these
localized fields and original human/monster skillsets and job references.

487 entries are eligible: 352 direct, 14 item, 12 throw, 12 jump, 8 aim, 8 math,
30 reaction, 28 support, 23 movement. The other 25 are unnamed/unused, explicitly
UNUSED, placeholder A-number labels, undefined types, or marked for deletion.
For example 184 has a native/WOTL reference but its localized description says
UNUSED; this is excluded for that reason, not because its original class is
unplayable. Every entry and exclusion is retained in ability-catalog.csv/.json.
Defined NPC, boss, and monster abilities with zero JP are eligible.

Allocation builds all 82 referenced human command plans and 48 monster plans
before applying scope flags. Seeded category decks use every ID before normal
repetition, avoiding row duplicates. Full mode supplies 6–12 actions and one
reaction/support/movement by default; limits are configurable. Native specialized
categories use compatible menu types (Default 0, Items 1, Throw 2, Math 3,
Jump 9, Aim 10). Flag x assigns these profiles across jobs; partial degree
retains original menus and list sizes. Monster lists stay within four slots
and receive any defined direct action, not only monster-source attacks.

Abilities depend on native learned flags, supplies, equipment, animation and
sprite behavior. Math parameters do not themselves grant every math-compatible
spell. Menu-compatible allocation and successful startup do not prove every
action can execute on every actor. These restrictions are recorded rather than
silently narrowing the catalog to caster spells.

### Opening encounter provenance

Enhanced `0002.pac` contains `fftpack/battle_entd4_ent.bin`; 0000.pac is not its
source. Extracted file length is 81920 bytes, SHA-256
`ba5f65ba5dc57bf528389922b7d48fa3571d5a1f4f24b1313aa1365399f162be`.
It has 128 entries (global 384–511), stride 0x280, 16 units at 0x28 bytes each.
Orbonne is global 387/local 3. Unit zero starts at offset 0x780: Ramza job 2,
command 26. Agrias uses job 52/command 33; Gaffgarion job 23/command 32;
ordinary Knights job 76/command 7. Thus job-table changes cover the opening
without editing its units or scripts. This file was inspected only, not patched.

### Historical 0.2.0 and removal of caster starter bias

0.2.0 expanded scopes but used only 110 ordinary direct actions and forced
several cheap spells into randomized lists. Its live launch applied nine XML
and eight Nex tables; every cell in actual loader-merged Nex output matched the
generator. Evidence is in research/live-validation-0.2.0; runtime 214.7 seconds.
The user's gameplay feedback showed the visible caster bias. 0.3.0 replaces that
pool with the full catalog and removes forced starter selection entirely.

Optional b now samples three paid physical direct actions and three other paid
direct actions, then changes only their global JP/CT/MP costs. It never changes
job allocation and is **off by default**. Baseline locale tables and pack hashes
are cached beneath research/preview-inputs; conversions verify every row and
cell. Default 0.3.0 emits no Nex files or cost overrides. The loader deletes old
generated modded*.pac files during initialization (FFTOModPackManager.cs 149–152).

### Real-loader validation of complete allocation

Installed seed 89f597b5, flags jsumxpw, spread 50%, full degree, actions 6–12,
one passive per type. All **487 eligible abilities** appear in its allocated
skillsets; no eligible IDs are unassigned. j/p/w stream results match 0.2.0.
The old installed seed was copied to
research/backups/installed-seed-before-0.3.0-20261009T135105Z and retained at
`C:/Reloaded-II/RandomizerBackups/20261009T135105Z/fftivc.randomizer.seed`.
A complete same-volume staged directory swap preserved Reloaded-II dependency
metadata and removed all previous caster cost overrides.

Fresh log `2026-10-09 13.51.06 ~ FFT_enhanced.txt`; saved as
research/live-validation-0.3.0/reloaded-complete-catalog.log. Structured result,
deployment and actual installed-loader serializer checks are alongside it.
All nine XML tables applied; JobCommandData had 1379 loader diff changes,
MonsterJobCommandData 151, JobData 1792, CommandTypeData 34. No error, exception,
conflict or stale Nex-cost processing appeared. Loader initialization 742 ms.
The game remained responsive for 305.2 seconds and closed gracefully. Original
executable and all eight catalog-input archive hashes remained unchanged.
The existing primary Decode-pattern warning and successful DecodeAlt fallback
remain. No battle execution or save input was performed by the agent.

Nineteen tests passed, including full catalog coverage, sane configurable
capacities, native category consistency, independent job scopes, 40 seeds,
determinism, sparse patches and real YAX deserialization/regression checks.

## Faster gameplay-test workflow research — 2026-10-09

Read-only investigation; no save, randomizer payload or installed mod changed.
[Ivalice Companion](https://github.com/sam-derby/Ivalice-Companion) documents
Steam Enhanced save editing for party/jobs/abilities/equipment and story progress.
Its release notes describe rebuilding story members, guests, world-map state
and progression flags for a chosen story step. This supports preparing a reusable
post-intro world-map test save, subject to an actual game-load validation.
The editor has not been run against this installation or randomized skillsets.

Important source-only layout evidence from
`crates/save-format/src/manual/unit_record.rs` on that repository's main branch:
unit records are 600 bytes; unlocked jobs are 24-bit at record +0x2F;
learned ability flags are 22 groups of three bytes at +0x32; packed job levels
start at +0x74; JP and total JP arrays at +0x80/+0xAE; active R/S/M IDs at
+0x08/+0x0A/+0x0C. These are offsets inside decoded save unit records, not
runtime RVAs. They have not been independently checked against a local save.
Personal jobs share Squire's progression slot zero according to this source.

`crates/domain/src/ability_flags.rs` maps native learned positions 0–15 and
18–23, but derives available controls from its imported vanilla job members;
its validation specifically expects Mime's original member list to be empty.
Thus ticking every listed vanilla ability is not a verified way to unlock all
of a randomized job's added occupied slots. A test-save helper should derive
learned-bit positions and equipped R/S/M IDs from our current job allocations,
preserve reserved bits, and leave the randomizer's lists and native costs intact.
The external editor's displayed ability names can differ from the modded game.

The FF16Tools ffto layouts include DebugSceneSelect, DebugGameFlowSettings and
DebugMap. The first two are fieldless layouts; DebugMap has one unknown integer
after comments. Their presence does not establish an accessible retail debug
menu, battle warp or working cutscene-skip feature. OverrideEntryData exposes
job, secondary skillset, R/S/M, equipment, level, bravery/faith, positions and
formation flags, but a dedicated test encounter still requires implementation
and runtime validation.

Proposed workflow: a copied post-intro world-map save with mastered ordinary
jobs, correctly unlocked randomized slots and stocked gear; short repeatable
battles; separate fixtures for unique/monster actors; ability batches with
coverage recorded by ability, actor, menu, equipment and passive trigger.
Use a fresh battle after each seed change. Preserve authored CT/MP costs for
normal verification, supplying adequate MP/items instead of making every action
free. No custom test arena or automatic battle-execution harness exists yet.

## 0.4.0 RCC rebuild (2026-10-09)

Reference checkout: I:/rumble_chaos_crashdown, commit
ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070, RCC version27. The user explicitly
requested RCC's complete pool setup/consumption and then its equipment rules,
with encounter randomization disabled. This supersedes the proposed strict
global one-owner allocator. BalancedDeck and fixed6-12 lists are removed.

RCC randomizer.py3594-3722 exchanges subsets of positive-JP actions between
existing command lists. Free actions stay through the exchange. Unique RSM
allocation samples reusable candidates; generic RSM allocation tracks a done
pool, reserves Poach471 for Thief, and has RCC's refill exception. Its final
SkillsetObject.mutate_abilities1720-1776 can introduce rare reusable actions or
RSMs. Native Items/Aim/Geomancy/Jump/Iaido/Throw/Math menus stay in place. Monster
mutate1134-1168 uses monster ranks11/12 of the time and the broader pool1/12.
No universal nonreuse or complete catalog coverage promise is made.

Catalog provenance is player352, shared3, creature132. IDs75Zodiark,
154Ultima,166UnholyDarkness are shared. Domain pools include shared IDs in both;
RCC's normal distribution and exceptions still govern actual allocation.
MasterTeleport499 receives RCC's9999JP setup before later JP mutation and may
appear in passive lists despite its original creature provenance. Populated
secondary/unreferenced command records are included, as RCC works on skillsets.
The port retains all16human action/sixpassive and fourmonster slots; original
job-to-command mappings are untouched.

### Additional native layouts verified on the supported executable

| Table | Raw offset | RVA | Stride | Entries | Baseline SHA256 |
| --- | --- | --- | --- | --- | --- |
| AbilityAttributes | 0x787A20 | 0x789620 | 20 | 368 | f477eb0b3ee33e9841065ca332c65cebc9abd065295ef3f2550d0e1544e922b7 |
| ItemConsumableData | 0x80DF70 | 0x80FB70 | 3 | 14 | b406d963ad500b69c4703dd3390adb6969d021f03baa239c20c8dd49c22f2250 |
| ItemEquipBonusData | 0x80E2A0 | 0x80FEA0 | 26 | 85 | b9bb1e612d34a0c696b514a7507af8641c99d38dd4e3bfeb970fdb23e7d4ed2b |

Action rows expand RCC's14byte format to20bytes. Cure row1 anchors the unique
signature04 01 01 00 00 E2 00 00 0C 00 0E 00 04 06 00 00 FF FF FF FF,
with tablebase one row earlier. Cure/Cura/Curaga/Curaja formula12, Raise formula13,
Reraise11, Fire8 cross-check the candidate. Native sword155 Flags4bit3,
MateriaBlade257 Flags4bit2, randomhits169 Flags2bit3 were verified. Extra six
bytes remain untouched. Native attributes are merged with nonnegative scalar
and array-element overrides from OverrideAbilityActionData before mutation;
negative/missing override values preserve the native field. Most original
NXD values are-1, so they cannot be treated as a complete baseline.

New read fields: ItemRequiredLevel byte2, EquipBonusId byte7; WeaponRange byte0,
Formula byte2, OptionsAbilityId byte7. Bonus rows0..73 follow RCC mutation;
empty/unreferenced74..78 receive fixed+1PA/MA/Speed/Move/Jump; added79..84 remain.
Item sentinels254/255 remain. EquippableItems uses40nativebits; optionali mutates
the original32bits and preserves the fifth byte. Private job traits read creature
portrait/palette/graphic bytes46..48 and big-endian innate/start statuses27..31
and37..41. Original LearnChance byte2 in AbilityMetadata is now retained privately.

### Read-only context and output adapters

Enhanced0002.pac supplies fftpack/battle_entd1_ent.bin through entd4_ent.bin,
each128entries *16units *40bytes. Original0004.pac supplies GeneralJob and
OverrideEntryData. Their effective original records provide5,312 occupied units
and150ranked jobs; RCC's stat feature ranks and transitive unlock-JP ranks use
these native inputs. Unit graphic0, level3, job10, enemy flagbyte24bit4 are read
only, with the independently verified Orbonne387 record as a layout anchor.
No encounter files/overrides are emitted. Source/table hashes are in
research/rcc-context/<input-hash>/inputs.json and the generated manifest.

RCC'snormalhelper, bitmutation, actionattributes, jobstats, JPdraws, weapon,
equipment/shop/status methods and complete human exchange/passive phase are
compared against dynamically loaded original source in tests. Python3 seed
streams and expanded TIC input tables are adapters; PS1 seed bytes are not
reproduced. TIC explicitly undefined/deleted entries are excluded as candidates.
AI learn-chance draws are calculated to preserve RCC JP phase RNG consumption
but cannot be safely emitted through the installed AbilityData manager's flags
bug. JPcosts use all seven localized Ability Nex tables. Full job innates,
creature innates and ability-status mutations remain separate unfinished phases;
i/y currently expose equipment permissions/weapon statuses only.

### Deployment and real-loader result

Seed89f597b5 is retained. The authorized rebuild changes rules and controls to
flagsjsumapw, RCCnormalrandomness25%, abilitydegree100%, chaos1. Old x/count
controls are retired. j/p/w now follow RCC rather than their old50%bounded-stat
streams. Output: outputs/seed-b07316a7da59. Changes:3,075public properties,
283JP IDs and275action-override IDs;466distinct eligible IDs occur in skillsets.
There are no fallback rank/attribute warnings in the ability audit.

Previous installed0.3.0 seed copied to
research/backups/installed-seed-before-0.4.0-20261009T150040Z and retained at
C:/Reloaded-II/RandomizerBackups/20261009T150040Z/fftivc.randomizer.seed.
Full same-volume staged folder replacement preserved Reloaded dependency data.

Thirty automated tests pass, including the actual installed serializer and its
negative AbilityId1 regression. Real Reloaded launch log:
%APPDATA%/Reloaded-Mod-Loader-II/Logs/2026-10-09 15.00.41 ~ FFT_enhanced.txt.
Ten emitted XML and eight Nex tables applied; no deserialization errors,
failures or conflicts. Actual merged modded*.pac Nex data was extracted and all
rows/cells matched the generated edited database. Loader initialization1486ms;
game responsive113.3seconds, own PID11148 gracefullyclosed. Original EXE and
numbered input archives unchanged. Existingwarning CFILE_DAT__Decode not found
remains; DecodeAlt matched. This is startup/data validation only; no battle or
save was operated by the agent. Evidence: research/live-validation-0.4.0.

## 0.4.1 audit: retained commands and missing passive categories

The user's 0.4.0 observations prompted a source and installed-payload audit.
Installed XML hashes/vectors matched seed89f597b5; no passive fields were lost
in deserialization or installation. RCC's BANNED_SKILLSET_SHUFFLE (source191-192)
explicitly protects Aim command8 and Jump command18. Its final source3716-3722
only removes individual protected parameters at1/8 odds; it does not trade them
for unrelated actions. In 0.4.0 Archer retained7/8Aim parameters, while Dragoon
retained12/12Jump parameters. Other lists exchange a subset and can retain much
of their original membership; 100%degree means RCC's original probabilities.

RCC ordinary passive assignment3664-3711 samples from a combined R/S/M pool,
without guarantees for any category. Its count can be zero (1/32 before supply
limits, except Thief); unique commands with no original learned passives stay
empty. The original0.4.0 Squire had36available pool candidates remaining and a
10candidate union, but drew zero. This was not exhaustion. Across19nonMime
ordinary jobs,5lacked a reaction,5lacked a support,7lacked a movement; Squire was
the only one with no learned passive at all. Mime is separately unchanged.

Two actual port setup errors were also found and corrected:

1. Name-based bans incorrectly added473BeastTongue,478Beastmaster and509Treasure
   Hunter to RCC's numeric exclusions. The exact source list is443,471,481,484,
   485,497. Restoring the three IDs expands the effective learnable pool from76
   to79 after MasterTeleport499's setup. Enhanced localized Reequip480cost50
   remains an intentional positive-cost native adapter (raw metadata cost0).
2. The action exchange used raw donor lists without the catalog's eligibility
   filter. Unused WOTL remnants357(from224) and358/361/363(from225) spread into
   Dancer23 and Cloud41. The PS1 source explicitly bans357..366 and asserts they
   do not occur in its skillsets; our synthetic all-eligible comparison fixtures
   did not cover FFTIC's legacy donor rows. Eligible-only donor discovery,
   contribution tracking and pulls now preserve original excluded rows but do
   not transfer their excluded IDs. Validation rejects any new excluded owner.

Verified localized evidence: IDs184/219/220/357..366 have EnglishDescription
UNUSED, null names in all seven locale tables, IconId0, UiId/UiId2=0 and empty
voice lists. Positive native JP/formula values are legacy data. Job160..168 rows
also have null localized names and no effective original encounter users;
169..173 are actual encounter monster jobs and remain active. Excluded passives
443/481/484/485 are unnamed/UI-unavailable; their descriptions are not uniformly
UNUSED. The source rows are preserved; execution of these remnants is unverified.

New regressions cover the exact numeric passive bans, excluded transfer across
41seeds, and disabled-phase preservation. All eight direct source-comparison
tests still pass, and the full suite contains33tests. Another164seed/scope
checks introduced no excluded IDs. Source comparisons remain separate from
gameplay verification. No minimum passive count/category rule was introduced.

Regenerated output: outputs/seed-68dd1b985af3, version0.4.1. Seed89f597b5,
flagsjsumapw, randomness25%, degree100%, chaos1 are unchanged. All equipment,
shop and job-stat XML values match0.4.0 exactly. Skillset and dependent ability
cost/compatibility results change as the corrected source pools consume RNG.
The corrected seed can still give Squire zero passives and Archer no supports.
This is allowed by RCC; there is no promise that a seed eliminates such results.

The prior mod and eight generated overlay packs are backed up under
research/backups/installed-seed-before-0.4.1-20261009T153721Z; same-volume mod
snapshot: C:/Reloaded-II/RandomizerBackups/20261009T153721Z/fftivc.randomizer.seed.
Live evidence is recorded under research/live-validation-0.4.1.

Fresh loader log: 2026-10-09 15.37.22 ~ FFT_enhanced.txt. All ten XML and eight
Nex tables applied without errors/conflicts; every actual merged Nex row/cell
matched. Original EXE and numbered archives unchanged. Loader initialization
1507ms; responsive for 105.7 seconds; own PID22420 gracefully closed. Existing
Decode warning remains and DecodeAlt matched. Thirty-three tests passed in
23.276 seconds. No battle or save input was performed by the agent.

## 0.5.0: RCC shuffle and Full redistribution

The user requested two ability modes, refill after exhaustion in Full mode,
and major-change validation rather than a launch on every iteration. RCC shuffle
remains the default and preserves its protected menu lists, probabilistic
exchanges, reuse exceptions and potentially empty passive categories. Full is
a custom allocation mode; the inspected RCC checkout does not establish a
separate total-ability toggle.

Full plans fresh lists for 90 humanoid command owners, 25 creature owners stored
in the human-format table, and 48 four-slot monster commands. The default human
action count is 6-12 with one reaction, support and movement; controls permit
1-16 actions and one or two per passive type. Native profile pool sizes cap
action counts. At lower ability degree, a seeded fraction of complete owners
is replaced, avoiding an incompatible mixture of command execution types.
The creature pool has no native reaction/support categories, so none are
invented; its available movement IDs are 497, 499 and 505. Four-slot lists keep
the fourth Beastmaster action slot.

Each compatible category/profile deck consumes every candidate before refilling.
Generated rows cannot repeat an ID internally. Player and creature decks are
separate except the catalog's shared IDs 75, 154 and 166. Items, Throw, Math,
Geomancy, Iaido, Jump and Aim remain complete compatible execution profiles;
Full can transfer those profiles to different humanoid owners. Native inventory,
terrain, katana, weapon and learned-spell requirements still apply.

Full also updates selected command Name, Description and Description2 cells in
all seven localized JobCommand tables. It preserves IconId, Unknown14,
Unknown1C, UiDialogId and DLCFlags. Direct lists get localized Randomized Actions
text, while special profiles use native localized donor labels. Original names
remain in job-abilities.json alongside the generated labels. CommandTypeData
XML records the corresponding execution menu changes. No new native addresses
or executable patches are introduced.

Flag correction requested by the user: s covers ordinary, unique, story and
unplayable humanoid skillsets together in both modes. The former custom u
unique-skillset option is removed. u is reserved for RCC's enemy/ally unit phase
and is rejected until that phase exists. The old jsumapw configuration therefore
becomes jsmapw, retaining the same enabled content. Shared job-stat, action,
equipment and shop phases retain their source behavior. Encounter, event, save,
unlock and reward data is not emitted by this release.

The first final-suite attempt exposed an open SQLite handle in a newly added
test's database context. sqlite3.Connection's context manager commits/rolls back
but does not close it. The test now uses contextlib.closing; production preview
connections already used explicit closure. Final runtime results follow below.

### Final seed, deployment and live result

Output outputs/seed-7993cbd0c84c uses retained seed89f597b5, Full mode,
flagsjsmapw, randomness25%, abilitydegree100%, chaos1, 6-12 actions and one of
each humanoid passive type. It changes 4,159 public properties and assigns all
487 eligible catalog IDs across the 163 command owners. Equipment/shop XML
matches the prior 0.4.1 seed exactly. All XML/NXD table bytes also match the
earlier Full candidate before merging the flag; only settings/report content
and the resulting output fingerprint change. RCC mode's same-seed table changes
and JP updates match 0.4.1 after translating old jsumapw into jsmapw.

Forty-six final tests passed in34.577seconds. All eleven XML tables passed the
installed 1.7.5 loader's actual serializers. The previous mod and eight overlay
packs are backed up under
research/backups/installed-seed-before-0.5.0-20261009T161456Z; same-volume mod
snapshot C:/Reloaded-II/RandomizerBackups/20261009T161456Z/fftivc.randomizer.seed.
Staged folder replacement preserved Reloaded configuration extras/dependencies.

Fresh log: 2026-10-09 16.14.56 ~ FFT_enhanced.txt. Eleven XML and fifteen Nex
tables applied without errors/conflicts. All seven Ability tables, all seven
JobCommand tables and OverrideAbilityActionData were extracted from the actual
merged modded packs; their schemas and every row/cell matched generated data.
Initialization1657ms; game responsive47.6seconds; own PID58428 closed gracefully.
Original Enhanced executable and all numbered input archives remain unchanged.
Existing CFILE_DAT__Decode warning remains; DecodeAlt matched. No battle or save
input was performed. Evidence: research/live-validation-0.5.0; deployment and
launch identities bind the exact seed manifest to the log/merged data receipts.
The generated manifest includes the runtime receipt. The source ZIP excludes
research, game data, catalog outputs, binaries and native caches.

## Encounter-generation investigation: RCC source semantics

Source inspected: I:/rumble_chaos_crashdown/randomizer.py, commit
ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070. Its displayed flag list is at 4997-5010;
the phase dispatch and per-phase reseeding are at 5107-5212.

| RCC flag | Source behavior |
| --- | --- |
| s | Humanoid skillset mutation, including ordinary and unique lists; independent of encounter-unit mutation. |
| u | mutate_units (3820): existing enemy and ally records across random and story templates. UnitObject.mutate (2466) changes stats, generic jobs, equipment, equipped R/S/M and secondary commands. Monster species/job substitutions occur here through mutate_monster_job (2379). |
| m | mutate_monsters (3809): monster job stats, innates and skillsets; it does not itself select different monster species for battle slots. |
| f | Formation/deployment records, encounter deployment areas and enemy/ally positions (5176 dispatch, 4114 placements). Can clone ordinary units into unused slots. |
| z | mutate_units_special (3881), special characters/encounters and other surprises. Combined z+f can replace eligible maps (5165). |

RCC rewrites finite existing ENTD/unit templates when generating its output ISO;
it does not create an arbitrary new roster on every battle visit. Native random
presence, automatic equipment and normalized-level encodings may still vary
when the game uses those generated templates.

Human job candidates are constrained by the original unit's inferred total JP
and job-unlock budget (jp_total at 2198; mutate at 2489-2555). Gender constraints
apply to Bard/Dancer. Named generic units keep a consistent job mapping across
appearances. Unique jobs outside the ordinary job tree normally retain their
primary job, while supported equipment/passive/secondary fields can change.
Loaded player-formation records skip equipment, secondary and R/S/M mutations.
Source sentinel values such as level 0xFE and auto-equipment values are semantic
encodings, not literal level 254 or item IDs to blindly shuffle.

The source tracks a historical nine-sprite map budget, reserves event poses,
and limits monster sprite families. Formation placement excludes unsuitable or
unreachable tiles, avoids occupied coordinates and scripted moving units, and
uses a heatmap for spacing and party distance. Extra-unit generation runs only
when at least six unused slots remain, leaving five after an addition. These
PS1 limits and numeric exception IDs are source constraints, not verified TIC
limits that can be copied unchanged.

FFTIC's verified 0002.pac contains fftpack/battle_entd1_ent.bin through entd4;
each is 128 templates x 16 slots x 40 bytes, totaling 512 templates. Existing
OverrideEntryData supplies keyed template/slot overrides and is already used
read-only by rcc_context.py. An encounter port must reconcile the binary records
with these overrides and identify random-battle ownership before emitting edits.
SpawnData/SpawnVariance are four global base-stat/equipment variance profiles
(male, female, Ramza and monster); they are not encounter roster selectors.
MapVariationRandomBattle's available layout name alone does not establish a
selector; its inspected fields expose DLCFlags and Comment.

A first random-battle implementation can preserve story records, placements,
counts, AI/script fields and event identities while applying RCC-style unit and
monster substitutions to verified random-battle templates. Formation/count and
special-surprise phases require separate terrain/script and runtime evidence.
No encounter randomization was implemented during this investigation.

## Version 0.6.0: RCC feature port and final installed validation

The earlier encounter investigation and 0.5.0 release are historical. Version
0.6.0 implements the pinned RCC v27 phase order r/i/s/a/y/j/m/u/z/f/t/p/w/c,
optional o, eight active patches.cfg defaults, built-in progression/cleanup,
and optional Fiesta/Easy Mode. Unique/ordinary humanoid skillsets share s.
Full redistribution remains the custom alternate mode. Detailed source,
layout, guard and execution evidence is indexed by RCC-PARITY.md and the
RCC-UNITS/FORMATIONS/INNATES/WORLD/SPECIALS/EVENTS/CONDITIONALS/QOL/QOL-EXTRA/
SECRETS documents. Classic, commented optional XML patches and PS1-identical
seed output are outside this Enhanced feature port.

Important newly verified runtime paths:

- Native Ability metadata RVA 787F80, 512 records x 8 bytes: JP ushort at 0, learn
  byte at 2, type/flags byte 3, AI uint at 4. The runtime preserves byte 3 to avoid the
  upstream AbilityData XML setter/manager type-nibble defect.
- Native Formation RVA 7AE2D0, 768 records x 12 bytes; Encounter RVA 8ECAB0,
  887 records x 24 bytes. ENTD inputs comprise four 128-template assets plus
  Enhanced 77 extra templates:589 templates x 16 slots x 40 bytes = 9,424 slots.
- Soldier Office party Rename uses modern mode 26/state 5EC, navigation type 6
  and presentation type 3; actual name commit RVA 2EF142..2EF1C2. Guarded edits
  remove only job-identity filtering at 2C0F37/29 bytes and 2C2217/26 bytes while
  keeping availability/status checks. The legacy mode 2 factory at 2850BD and
  states 4BB/4BC refer to other paths and are not emitted for party Rename.
- Smart Encounters guards/replaces the original 125-byte chance block at
  248CBF; native RoutePosition D8DC08/RouteLength D8DC0C equality supplies the
  destination/pass distinction while native force/chapter eligibility remains.
- Proposition unlocks use 7B768C, 96 x 23 bytes (unlock byte at 21); eight JP rewards
  are at 7B80C0. Special-character proposition predicate 2EE3B1 preserves the
  source exclusions. Fiesta Ramza starter job store 275392 is guarded through
  the verified recruitment chain; no new save format is introduced.

### Startup scanner ordering correction

The first 0.6.0 launch read back every patch/table/asset successfully, but its
early Reloaded native Init changed the signatures used to find AbilityData and
SpawnData. This caused two new scan warnings and was not accepted as final
validation. Both old packages and that launch audit are preserved under
research/generated-before-startup-bridge and
research/live-validation-0.6.0-before-startup-bridge.

Installed Reloaded IL proves LoadForAppConfig loads mods/dependencies, then
synchronously invokes OnModLoaderInitialized. The startup scanner registers
first and finishes FindPatternsCached, its callbacks, and blocking arbitrary
scans before returning. Nenkai registers next and applies packs/XML; the
dependent managed randomizer bridge registers last. Its callback loads this
project's C++ DLL and calls Init only after that barrier, with no fixed sleep.
Both ModNativeDll32 and ModNativeDll64 must be empty: either nonempty field
forces Reloaded's early native branch even when ModDll is set. ModDll now names
fftic-rcc-startup.dll. See research/reloaded-startup-order.md, component SHA256
receipt, scanner-barrier and mod-config-selection IL captures.

The 5,120-byte managed bridge targets installed .NET 9 and Reloaded interfaces 2.5;
the 164,352-byte native DLL retains its exact Enhanced SHA256 and original-byte
transaction guard. The source distribution ships both owned binaries, full
sources/build scripts and independent source/DLL hashes in native/runtime/
build.json. No Nenkai/Reloaded DLL was changed. Rebuild uses local MSVC and
PowerShell's Roslyn with explicit .NET 9 metadata, avoiding its newer host ABI.

### Final seed, evidence and boundaries

Installed outputs/seed-5a88e74dbf87 uses retained seed 89f597b5, Full mode,
flags risayjmuzftpwc, randomness 25%, degree 100%, chaos 1, 6–12 actions and one of
each human passive. Optional Fiesta/Easy Mode and custom b/dialogue o remain
off. There are 6,370 public property changes; all 487 eligible ability IDs are
covered. Same settings in RCC-shuffle mode produce 5,238 public changes under
outputs/seed-9ef05ab94b32. Numeric source-seed identity is not claimed.

The 124-test main suite passed in 698.601 seconds; 10 subsequent focused checks
passed in 9.024 seconds for corrected active Rename, native guards/execution and
prepared unit-context immutability. The managed bridge compiled against actual
local interface metadata and Python syntax checks passed after integration.
All 14 emitted XML tables also passed the actual installed 1.7.5 serializers.

Final deployment backup:
research/backups/installed-seed-before-0.6.0-20261009T191636Z;
same-volume snapshot C:/Reloaded-II/RandomizerBackups/20261009T191636Z/
fftivc.randomizer.seed. The original 0.5.0 installation is retained in the earlier
20261009T190120Z snapshot. Unknown Reloaded config fields were preserved.

Final launch 19:16:37 UTC, own game PID 59776: AbilityDataTable and SpawnDataTable
matched their untouched signatures; the bridge then applied all 23 guarded
native ranges after the last XML application. Actual runtime readback matched
every native/XML field, every row/cell of all 34 emitted Nex tables, and all 15
binary/script assets extracted from the loader's merged packs. No errors or
conflicts; the existing CFILE_DAT__Decode warning remained with DecodeAlt found.
The game was responsive 69.6 seconds and closed gracefully. All 37 original EXE
and numbered archive SHA256 values stayed unchanged.

Final Full manifest SHA256:
75419f71deaaeb865ad6cf71ed9d8051c0bec4f2f43b5c6729ef7045c5b345c2.
Receipts/logs: research/live-validation-0.6.0. This confirms startup and applied
data, not battle execution, shop/proposition/rename interactions, save behavior
or campaign completion; no gameplay or save input was performed.

## Version 0.6.1: Enhanced buried-reward generation fix

User reproduction: seed `f6745fb4`, RCC shuffle, flags `risayjmuzftpwc`, stat
randomness50%, degree100%, chaos1, Fiesta enabled, Easy Mode disabled. The
original map75/slot4 contains common256/rare256, X8/Y9, trap flags2. The normal
reward branch rejected256 because public ItemData covered only0..255 and RCC's
eligible ranks only1..253; the special branch could replace it without reading
its metadata. This made the failure seed-dependent.

Verified `Item-en` names256 **Materia Blade+**,257 Akademy Blade,258 Akademy
Beret,259 Akademy Tunic,260 Ring of Aptitude. The loader supports these five
separate12-byte ItemDataExtended rows, discovered at raw67F510/RVA680510 with
signature `0D 15 61 82 20 03 00 54 0A 00 01 00 0D 0C 08 82` and complete-table
SHA256 `696e9758bf0cccbad5bc404082dd3cf8b92c11d10dcd68915aadd0fa2474c849`.
Materia Blade+ has price10, RequiredLevel97, AdditionalDataId32, EquipBonusId84.
It is a real Enhanced item; IDs254/255 remain random/empty sentinels.

The reader now attaches `_ExtendedItemData` without merging it into public
ItemData. The buried-reward allocator uses an extended baseline item's `(rank,
ID)` insertion position in RCC's eligible ranks, clamped at the last index,
then applies the existing reverse-rank boost and normal mutation. Returned
items remain in1..253; the source's special full iterator still allows0..253.
Thus Materia Blade+ is randomized while unit equipment and trophy byte fields
cannot receive oversized IDs. Ordinary reward results and RNG draws are
unchanged. No new runtime patch or loader DLL change is introduced.

Five regression checks plus the six existing world/source comparisons passed:
11 tests in1.592seconds, receipt research/reward-error-f6745fb4/tests.txt.
Actual user seed output: outputs/seed-2e0c50235575,5638 public changes.
ManifestSHA256 `0744054e5797e9cc9845abb072bf8cba587eb3ddfa551b5a5c8598d37d2afbf8`.
All13 XML tables passed the actual installed loader serializers. Real Reloaded
launch19:43:57UTC/PID61112 passed all24 native ranges (including Fiesta), all13
XML tables, all27 merged Nex tables and15 binary/script assets. No errors or
conflicts; only the existing Decode warning remained with DecodeAlt matched.
The game responded113.3seconds and closed gracefully; all37 original input
hashes remained unchanged. No gameplay/save input was performed.

Temporary validation backups are under
research/backups/installed-seed-before-0.6.1-20261009T194348Z and
C:/Reloaded-II/RandomizerBackups/20261009T194348Z/fftivc.randomizer.seed.
After validation, the original installed0.6.0 Full seed and eight overlay packs
were restored and compared byte-for-byte with those backups. The tested0.6.1
installation is also retained at C:/Reloaded-II/RandomizerBackups/
validation-completed-20261009T194628Z/fftivc.randomizer.seed. Launch/readback/log/
restoration receipts are under research/live-validation-0.6.1-f6745fb4.

## Version 0.6.2: standalone application, clean labels and control help

The public mode now reads **Shuffle**; the internal `rcc` value remains stable
and is also accepted as a legacy CLI alias. Repeated source-brand prefixes were
removed from setting labels, mod descriptions, human-readable reports and native
patch labels. Source audit keys, payload magic, runtime filenames and technical
source references remain compatible. About / Credits, generated CREDITS.txt,
THIRD_PARTY_NOTICES.txt and bundled licenses credit Rumble Chaos Crashdown,
FF16Tools, the mod loader/layouts, Gibbed and executable runtime components.

The GUI provides delayed hover and keyboard-focus descriptions on all34
interactive controls. Tooltip dismissal on leave, clicks, scrolling and widget
destruction, negative monitor origins, mode changes and the responsive footer
passed focused Tk checks at1120x900,800x600 and520x340 with9pt/16pt default fonts.
The notices view is scrollable and read-only. These are UI checks, not gameplay.

`runtime.resource_root` separates immutable one-file resources from persistent
workspace caches. Frozen caches use %LOCALAPPDATA%/FFTIC Randomizer; default
outputs use the user's redirected Documents/FFTIC Randomizer/Seeds. Nearby game
folders and Steam's registered libraries supply the initial game-folder field.
All cache readers/writers receive the same persistent project_root. Absolute
world/name database paths are refreshed on cache reuse. Report labels now come
from the installed English archive rather than a developer names.json file.
Bundled converter children use their own directory, bundled .NET root and
persistent extraction cache, with console windows hidden. Frozen native runtime
integrity failures reject generation instead of requiring a local compiler.

The build tool `tools/build_executable.py` creates a windowed one-file Windows
x64 executable. It verifies official FF16Tools1.13.3 and .NET9.0.20 archives and
their extracted contents, validates both native runtime receipts, and bundles
only explicitly allowed resources. Python3.13.13/Tk and PyInstaller6.22.3 are
included. Full runtime/converter/NuGet notices are embedded and supplied in the
portable ZIP. Artifact audit found2420 embedded entries, no game archives,
SQLite extraction databases, research directories or PDB debug symbols.

Executable: outputs/FFTIC-Randomizer-0.6.2/FFTIC Randomizer.exe,
55,071,114bytes; SHA256
ca74d5f8c78a6f55a07ad6d07424ef04b0b9098ec04343ce4575d67927aa5ed2.
Portable ZIP: outputs/fftic-randomizer-0.6.2-windows-x64.zip,54,662,185bytes.
The actual no-argument exe opened its complete65-child Tk GUI and responded.
The owned GUI PID61592/bootloader58420 closed through a normal WM_CLOSE sent to
the current PID-verified TkTopLevel; an initial .NET CloseMainWindow check was
inconclusive because its earlier window handle was no longer current.

Cold-cache frozen generation used an empty isolated workspace, Windows/System32
only on PATH, no PYTHONPATH/external converter override, and unavailable global
.NET roots. The converter trace confirms `_MEIPASS/vendor/dotnet`9.0.20. Seed
f6745fb4, all normal flags, Shuffle,50% randomness and Fiesta generated5638
changes in115.56seconds: outputs/portable-validation/seed-2643d481788c.
All61 payload hashes and ZIP contents matched the manifest. All55 actual game
data files (13XML,27Nex,15binary/scripts) were byte-identical to the real-loader-
validated0.6.1 seed; all24 native ranges/expected/new bytes were semantically
identical, with only labels differing. Both runtime receipts passed and the35
checked original input hashes stayed unchanged. No installed mod, game launch
or gameplay/save input was performed during this packaging validation.

Evidence: research/frozen-validation0.6.2/result.json, process.json,
originals.json and converter-runtime.trace; research/executable-build/
artifact-audit.json, gui-startup.json, build.log and the portable build receipt.

## Native Linux distribution, 0.6.3

Linux runtime paths use native/Flatpak Steam library discovery, XDG cache and
Documents locations, platform-specific converter selection, and xdg-open with
the frozen application's library path restored. Windows defaults are retained.
The local regression suite passed 140 tests, including Linux path fixtures.

The Linux converter builds pinned FF16Tools 1.13.3 with a bounded CPU GDeflate
adapter. It validates stream framing and output capacity before calling the
pinned Microsoft/NVIDIA page decoder. Native and managed tests cover 24
synthetic streams, invalid input and output guards. Synthetic PAC extraction
and SQLite/NXD round trips exercise the published CLI. Lowercase layout aliases
preserve exact upstream contents while allowing Linux filename lookup.

The same CPU decoder was compiled diagnostically on Windows and checked
against all 11,907 entries in 16 installed Enhanced archives (0002, 0004 and
0005 plus locale archives). All stored CRCs and decoded lengths matched;
original archive hashes were unchanged. No extracted game data was retained
or included in public fixtures. This confirms archive compatibility, rather
than Linux game loading. Evidence: research/linux-converter/archive-check.json.

The manual Linux workflow targets Ubuntu 22.04/glibc 2.35. It builds the native
converter, bundles Python/Tk and a self-contained .NET runtime, and checks
frozen GUI startup under Xvfb for both AppImage and portable tarball. The build
receipt records input hashes, native dependency checks and startup results.
The game and mod runtime remain Windows components executed through Proton;
an actual Steam Deck game launch remains unverified.
