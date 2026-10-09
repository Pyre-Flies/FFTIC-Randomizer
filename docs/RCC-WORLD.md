# RCC requirements, rewards and world data

This records the Enhanced FFTIC adapters for RCC's `r`, `t`, and `c` phases,
plus the native encounter/deployment records shared with the formation and
special-event phases. The original executable and archives are read only.
Native changes are returned to the packager as guarded runtime memory patches;
Nex changes and supported loader tables use their normal overlay paths.

The source is the user's `rumble_chaos_crashdown` checkout, commit
`ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`. Python 3, extra Enhanced records,
and adaptations below mean a seed is not identical to the PS1 result.

## Verified native tables

These offsets apply only to Enhanced executable SHA-256
`937233f7fe76182a665c487c8802f5cec6662ddd09967e87cd09fb146fc6b5d5`.
Readers also require unique signatures. An RVA is relative to the loaded
module base; no executable bytes are replaced on disk.

| Table | File offset | RVA | Layout | SHA-256 of complete table |
|---|---|---|---|---|
| JobNeedLevelData | `0x67E390` | `0x67F390` | 22 rows × 12 bytes | `641daa0244bf8d0ca19aada3f6a58018726004dc74a7ce430bb7ce11fb2873f5` |
| ItemDataExtended | `0x67F510` | `0x680510` | 5 items × 12 bytes | `696e9758bf0cccbad5bc404082dd3cf8b92c11d10dcd68915aadd0fa2474c849` |
| MapTrapFormationData | `0x781C40` | `0x783840` | 128 maps × 24 bytes | `543e7381046cfddf00d032f71aabb784c93b3a7373b289f8a6f99af8d49f8cea` |
| Formation | `0x7AC6D0` | `0x7AE2D0` | 768 rows × 12 bytes | `41927126a6072d24446a132f3f77e75a91def2506b811471360c4c0f11582382` |
| Encounter | `0x8EAEB0` | `0x8ECAB0` | 887 rows × 24 bytes | `e1d142929f47b432f09c50c1a7e89c5e97ea65540fde87374aedf1cf74e951fc` |

JobNeedLevelData and MapTrapFormationData layouts and signatures come from
Nenkai's loader source, commit
`c74047dc1b36bfe1bf6a466cf3645f1fe9815425`, specifically the matching
`Interfaces/Tables/Structures` and `Tables/FFTO*DataManager.cs` files.

JobNeedLevelData packs two prerequisite job levels into each byte, high
nibble first. Fields follow Squire, Chemist, Knight, Archer, Monk, WhiteMage,
BlackMage, TimeMage, Summoner, Thief, Orator, Mystic, Geomancer, Dragoon,
Samurai, Ninja, Arithmetician, Bard, Dancer, Mime, DarkKnight, OnionKnight,
Unknown1, Unknown2. Native row0 belongs to Chemist; rows0..18 therefore map
to native jobs75..93. Rows19..21 are extra WOTL/unused requirements and are
preserved. The signature starts at row16; discovery subtracts192 bytes.

MapTrapFormationData contains four six-byte slots per map. Each slot is:
packed XY byte (`X << 4 | Y`), trap flag byte, rare item ushort little endian,
common item ushort little endian. Public loader properties are
`X1/Y1/TrapFlags1/RareItemId1/CommonItemId1` through slot4. The signature is
map1; discovery subtracts24 bytes. Trap flags match RCC: bit0 Degenerator,
bit1 Deathtrap, bit2 SleepingGas, bit3 SteelNeedle, bit4 DisableTrap, bit5
AlwaysTrap, bit6 unused, bit7 NoActivation.

Formation fields are Bitmap uint little endian at0, X4, Z5, Zero6,
Orientation7, NumCharacters8, MapNumber9, IdNumber ushort little endian at10.
Orientation's high nibble is facing; the low nibble is rotation. Every native
IdNumber equals its row index0..767. The next record starts a different
table. Native pointers at file offsets `0x8EAE58` and `0x8EAE60` contain
`0x1407AE2D0`, independently linking the table to the encounter context.

Encounter fields match RCC's 24-byte record:
Scenario ushort at0, MapId2, Weather3, Night4, Music bytes5/6, ENTD ushort7,
Grid ushort9, Grid2 ushort11, Unknown0 uint13, Ramza17, NextScene ushort18,
Following20, Unknown1 byte21, Event ushort22. Native lookup code at RVAs
`0x20DFC0`, `0x2FB881`, and `0x2FBB6B` references this base, steps24 bytes,
and compares against capacity `0x377` (887). A zero Scenario terminates the
lookup. The original has713 filled rows followed by174 empty rows. Row2 is
Scenario3, Orbonne map56, ENTD387, music52/12, Event1. Enhanced added
scenarios/ENTDs beyond the original PS1 ranges; row indices and Scenario
IDs must be kept distinct. `event_btlevt_bin.bin` is an event-opcode pointer
file, not this encounter table.

## Requirements (`r`)

`rcc_requirements.py` ports `mutate_job_level` and
`mutate_job_requirements` (RCC3350–3527). It preserves the source's two or
three balanced branches, 19 generated ordinary jobs, maximum level8,
up to14 chosen prerequisites, transitive maximum requirements, and a mage
prerequisite for Calculator. Bard/Dancer cannot be prerequisites because of
their gender restrictions. It also raises item122/125 enemy requirements
to at least5, matching RCC's Gariland throwing-item protection.

The global eight-threshold curve uses Enhanced's original input
`100,200,400,700,1100,1600,2200,3000`, RCC's US difficulty multiplier
`1.5 ** chaos`, maximum per-level difference800, normal mutation and
rounding to multiples of50. Enhanced `GeneralJob.RequiredJobExp` includes
an initial zero before those eight thresholds. After thresholds change,
the unit agent's `prepare_unit_backups` runs in the same random stream,
using original prerequisites and the new JP curve, before the tree changes
(RCC5094–5096).

Supported native JobNeedLevelData receives the full prerequisite closure.
`GeneralJob` Nex arrays receive the immediate prerequisites after the same
transitive reduction used by RCC's displayed prerequisite dictionary.
Existing label positions survive; new labels use the verified valid native
position3. Unrelated UI connector/coordinate fields remain original. Their
appearance with a changed tree has not been verified in gameplay.

The private result exposes `_RCCOriginalJobRequirements` and
`_RCCJobRequirements`, keyed by native jobs74..93, plus `_RCCJobLevelJP`.
Partial selection gates a tree as a whole; independently mixing old/new
prerequisite rows could create cycles.

## Rewards (`t`)

`rcc_rewards.py` ports the source order: all unit gil/trophies, all poaches,
then all512 buried-item slots (RCC2217–2223,1169–1258,4606–4618).
It uses the original price/priceless item ranking, reverse-rank difficulty
boost, normal mutation, rare reward rank rules, and rare-poach reuse only
after unused higher-ranked candidates are exhausted. Item IDs254/255 are
FFTIC sentinels and cannot become rewards. Special buried-item common
choices include item0 because RCC's full item iterator includes it.

Enhanced map75, slot4 originally awards **Materia Blade+** (item256) as both
common and rare reward at X8/Y9, trap flags2. This is a real item in a separate
five-row ItemDataExtended table, not an empty/random sentinel. Its price10 and
RequiredLevel97 produce RCC's priceless rank74710. Version0.6.1 reads items
256..260 into private `_ExtendedItemData`, without extending public ItemData or
byte-sized ENTD candidates. For an extended baseline buried reward, its `(rank,
ID)` insertion position in the original RCC pool supplies the rank guide,
clamped to the last eligible item. The normal reverse-rank boost/mutation then
selects a replacement from IDs1..253. Source special selection retains IDs0..253.
Both branches randomize this slot without returning oversized item IDs; normal
item output and RNG draws remain unchanged. The source loader's extended-table
signature is `0D 15 61 82 20 03 00 54 0A 00 01 00 0D 0C 08 82`.

Unit fields are `TrophyItemId` at native byte30 and `Gil` at31. The unit
adapter owns the original ENTD blocks and asset emission. RCC's gil mutation
uses a65000 bound and rounds to hundreds, but the actual field is one byte:
the adapter clamps values above255 after source rounding. The PS1 source's
one-byte writer would otherwise reject them. Seed89's direct treasure test
required no such clamps.

Enhanced replaces the PS1 two-byte poach table with seven localized
`PoachItem` Nex tables. `Unknown2C` is the exchanged ItemId, independently
confirmed by FF16Tools' field-reference code and actual native rows.
`IconId` identifies native monster index+1 and `IsRare` selects common/rare.
There are96 carcass records for48 monsters. Carcass keys use Enhanced UI
sorting order: Bomb index6 uses keys25/26; Ghoul index18 uses keys13/14.
Thus consecutive pairs cannot simply be assigned to consecutive native jobs.
All seven locales receive the same exchange-target changes. Carcass names,
descriptions, prices, rarity and other fields are preserved; descriptions may
still mention the original item, while the exchanged item ID changes.

Buried-item relocation retains the source's half-time special choice and
terrain rejection. It uses `rcc_maps.certain_values(variants,'bad')`, with
scripted movers, largest reachable zones, lava/water plants, depth, slopes,
impassable and uncursorable cells. Cross-variant disagreement is `None` and
usable in RCC; that behavior is preserved. Some original TIC variants have
dimensions17/18, so candidates above15 are rejected to fit packed XY nibbles.
Missing terrain or no representable valid tile returns without further slot
changes. Trap-bit order, common/rare swap chance and preserved high bits
match the source.

## Music (`c`)

`rcc_music.py` ports EncounterObject.randomize_music (RCC985–1018) and its
dispatch5210–5215. It preserves the exact banned tracks, protected
`0xFC < ENTD < 0x180` range and24 sneaky-event ENTDs, one-percent exceptional
track35 chance, used-track avoidance, exhaustion reset, and the fact that
two slots may choose the same candidate. Its reusable helper also supports
the source's `prefer_unused` and `force_battle` options for special events.
Track reuse is source behavior, not an exclusive deck.

The result changes native encounter music bytes5/6, returned through the
guarded runtime patch plan. Other encounter fields are unchanged by `c`.
Track playback is not proved by table comparisons or loader startup alone.

## Integration and verification

`prepare_world_data(tables,game_dir,project_root)` attaches the public
requirements/trap tables, private `_RCCEncounters`, `_RCCFormations`,
`_RCCNativeWorldTables`, `_RCCGeneralJobs`, `_RCCPoaches`,
`_RCCPoachNexTables`, and `_RCCWorldInputs`. The world cache is keyed by
original0004 archive hashes and validates every extracted table/database hash.
It contains GeneralJob and all seven PoachItem tables.

`apply_requirements`, `apply_rewards`, and `apply_music` mutate the working
result. Sparse Nex changes are `_RCCWorldNexUpdates`, with table names,
tuple row keys, and changed column values; arrays are Python lists for the
packager to serialize as JSON. Call `commit_world_patches` once after all
world phases; it appends `{name,rva,expected:bytes,data:bytes}` to
`_RCCNativeTablePatches`. Call the unit adapter's commit only after rewards
and encounter phases have finished. It preserves every untouched native byte.

Six targeted tests compile methods directly from the user's RCC checkout.
They compare outputs and complete random-generator states for JP thresholds,
job trees, item/poach selection, buried coordinates/traps, and music bans,
protections and resets. A native-reader test changes one music byte and checks
that the patch changes exactly that byte. An original-input in-memory seed89
treasure/music check completed with48 changed poach owners,405 changed buried
slots,63 changed unit reward rows and459 changed encounter music rows.
These are adapter checks; deployment and gameplay verification belong to the
parent validation workflow and have not been performed by this subtask.
