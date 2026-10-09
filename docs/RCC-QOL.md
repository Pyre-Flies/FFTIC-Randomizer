# RCC default patches and Enhanced native equivalents

This document records the verified native adapters for RCC's active
`patches.cfg` and `free_soldier_office`. The plans are created by
`fftic/rcc_qol.py` and applied in memory by the guarded runtime mod. Generation
does not modify `FFT_enhanced.exe` or the installed archives.

The source is `rumble_chaos_crashdown` commit
`ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`, with the active configuration at the
repository root, rather than `tables/patches.cfg`. The native binary is the
Enhanced executable with SHA-256
`937233f7fe76182a665c487c8802f5cec6662ddd09967e87cd09fb146fc6b5d5` and PE
timestamp `6A5E4A1B`. Every address below is an RVA for that binary.

## Implemented plans

| RCC behavior | Enhanced plan | Evidence |
| --- | --- | --- |
| Fur Shop available from the start | Return1 for global flag144 in both native variable getters | Fur Shop menu consumer `344A07..344A40`; poach inventory consumer `36E9C9`; source initializes flag144 |
| Propositions available from the start | Return1 for global flag145 in both getters | Proposition menu consumer `2D4CDB..2D4D01`; source initializes flag145 |
| Double earned JP | Double the action's base JP before party spillover, scenario scaling and JPBoost | Native action gain function `28338C..283664`; source `abyssonym.xml`, BATTLE_BIN `117954` |
| Mighty Sword100% break patch | Replace the full Formula46 implementation, preserving its native stack frame | Source `Razele.xml`, BATTLE_BIN `122B94..122C50`; native formula dispatch and function guards |
| Free Soldier Office | Zero fixed recruitment fees and clear the seven male/female starting equipment bytes | Source `randomizer.py:4722-4738`; verified SpawnData12-byte profiles and fixed-fee call sites |
| Poach ability not required to enter Fur Shop | Existing Enhanced service behavior; no extra patch | Original Town constructor `3449B0` and Poach controller activation `1AF630` execute without party/ability data |

`free_soldier_office` runs when the flags intersect `rujimtpsazfyw`, as in
source `randomizer.py:5251-5265`. A run with only `o`, `c`, or the local testing
flag `b` does not activate that source conditional. The configured XML patches
apply independently of these randomization flags.

### Global unlock getters

The World getter is `2E9898`; the Battle getter is `2332D8`. Each starts with
`48 89 5C 24 08`, a single instruction saving RBX in caller home space. Its
replacement jumps to a21-byte trampoline that tests the unsigned value
`flag-144 <= 1`. Flags144/145 take a six-byte `mov eax,1; ret` leaf path.
Other inputs execute the original instruction and resume at entry+5. ECX and
the original getter's VM state handling are preserved.

| Scope | Entry | Trampoline | Return-one helper |
| --- | --- | --- | --- |
| World | `2E9898` | `5A731B` (21bytes) | `5A7368` (6bytes) |
| Battle | `2332D8` | `5B02BB` (21bytes) | `5B0252` (6bytes) |

The trampoline/helper locations must contain the exact expected `CC` bytes,
and must lie outside all `.pdata` runtime-function ranges. The code changes
what reads return; it does not rewrite saved global flags.

### Earned JP

Native base JP at `283587..283599` is
`(8 + level//4 + 2*jobLevel) & validActionMask`. The block at `283595` is
`40 80 E6 30 23 E9 33 FF`: mask the actor's team bits, mask base JP, then clear
the loop index. The15-byte trampoline at `410AC1` reproduces that block with
`D1 E5` (`shl ebp,1`) after the base JP mask.

Spillover JP at `2835A7` divides this doubled base by4. The acting unit's JP
then uses the scenario multiplier at `2835BB`, followed by native JPBoost at
`2835CB`, before both current and cumulative JP are increased by the guarded
native helper `283664`. Existing9999 caps and eligibility checks survive.
XP and proposition/crystal JP use other paths and are not doubled by this
battle action patch. RCC's separate proposition JP cleanup remains separate.

`DifficultyLevel.Unknown8/C/10/14` are damage/healing scaling fields, verified
at `30A07E`; they are not substitutes for this JP patch.

### Mighty Sword source control flow

The source XML's prose says these skills always deal damage, but the actual
MIPS branch at `122BC4` exits when an unprotected target lacks the selected
equipment slot. The port retains that branch. Safeguard prevents breakage and
continues to damage. The100% break roll still advances the native battle RNG.
Native synthetic equipment257..260 is protected as an Enhanced adapter.

The native dispatch base is `682BD0`, containing106 pointers indexed by
`formulaId-1`. Formula45 is `3084C4`; Formula46 is `308538..308663` (299bytes).
The original Formula46 function SHA-256 is
`24cf31dc124e77d5a65789c4fa77fa325e3fdad4fee038b39dd568ce7fad7522`.
The replacement retains `sub rsp,28h` and a matching native epilogue.

| Native helper/context | RVA / field | Role |
| --- | --- | --- |
| Native chance RNG | `278E68` | Range100, threshold100; zero means success |
| Gear selection | `3065C4` | Original per-ability slot, creature restriction, empty/synthetic slot handling |
| Physical accuracy/setup | `306C90` | Original prerequisites and hit/miss calculation |
| Caster source pointer | `186AF78`, PA at `+3E` | Native PA factor |
| Defender pointer | `186AF68`, Safeguard at `+9A` bit04 | Break protection |
| Target result pointer | `186AF70` | GearId `+4`, HP damage `+6`, action flags `+12`, selected gear mask `+1B` |
| Weapon power / action Y / element | `7B07AC` / `7B079E` / `7B07AE` | `(WP+Y)*PA`, then element modifiers |
| Native PA and WP+Y factors | `7B0770`, `7B0772` | Shared physical formula inputs |
| Damage helpers | `305BB8`, `306E34`, `305EB4`, `305F08` | Native boost, physical, zodiac and product calculation |
| Element and post-result helpers | `305554`, `306224`, `306944` | Native absorb/weak/half effects and cleanup |

The physical damage is divided by2 before element application, matching the
active source patch. The ability's original gear-slot selection is retained.
Ability distribution and cost randomization use the same native Formula46
adapter wherever the redistributed ability is learned.

The public [skeewirt/TIC formula research](https://github.com/skeewirt/TIC/tree/c2dae2a4be46f69e5a27008449d2299eff34ed0d/remaster/formulas)
provided useful search leads. Its older addresses do not match this
executable, and its `DualHitSetup` label for the gear selector does not match
the verified slot-selection behavior. The addresses and field meanings above
were derived from this exact binary rather than copied from that reference.

### Soldier Office

| Site | RVA | Original instruction/data | Change |
| --- | --- | --- | --- |
| Modern frontend affordability | `1AE6E1` | `cmp eax,1500` | Compare with0 |
| Native office affordability | `33343D` | `cmp dword[rax+348C],1500` | Compare with0 |
| Displayed fixed fee | `337197` | `mov edx,1500` | Use0 |
| Fixed debit | `3374CC` | `mov edx,1500` before `EBF88`/`EBFC4` | Use0 |
| SpawnData | `67F7D0` (48bytes) | Four12-byte profiles | Clear bytes5..11 and17..23 toFF |

Spawn profiles0/1 are male/female generics,2 is Ramza,3 is monsters. Source
stats and profiles2/3 remain unchanged. The seven cleared bytes are Helmet,
Armor, Accessory, RightWeapon, RightShield, LeftWeapon and LeftShield. The
call at `3374C3` is an unrelated UI event supplied by a missing-equipment
counter (`333884`); it is not an extra gil debit.

### Existing Enhanced Poach-free entry

The native Town-menu constructor `3449B0..344A61` checks global flag144 and
the localized Town field32 to display the fourth service label `B860` (Fur
Shop). The native Poach controller activation `1AF630..1AF7CC` enters state14
and sends opening cue `1B59`; its inputs are controller/UI state. Neither
function reads party abilities. A focused test executes both original native
functions in a synthetic image containing no party/ability data and verifies
the fourth menu entry and successful opening cue.

The World mode dispatcher `2C4880` routes Poach states to that controller.
The update path `36C874..36CB1B` polls `1AF7CC`, then routes its chosen states
back through `2C4880`. State14's top menu at `1B0CBE..1B0D45` selects buying,
processing or returning; the subsequent purchase path checks gil and stock.
This existing Enhanced entry behavior satisfies the source patch
`Razele.xml`/`WORLD_WORLD_BIN:57166`; no additional ability hook is needed.
The isolated entry test does not establish in-game shop interaction.

Exact-build RTTI inspection identifies `UIAgentFFTOPoach` at descriptor
`919738`, primary vtable `70B7D0`. Its shared open method `1980FC` and initial
state activation `1AF630` use UI visibility and controller fields. The
inventory setup `1AFFC4` uses the native stock and NexPoachItem rows. These
paths, rather than an absence of an immediate ability ID, establish the
existing entry behavior.

## Additional default paths

`rcc_qol_extra.py` owns proposition cleanup/rewards, the modern proposition and
rename eligibility paths, and destination-only Smart Encounters. The packager
combines both modules' audits and rejects any unresolved default before output.
The `o` decoder belongs to `rcc_events.py`; it merges DisplayMessage flag edits
with the working progression/ending assets. These ownership divisions are not
additional user feature flags.

## Validation

`python -m unittest tests.test_rcc_qol_native -v` passes six focused tests.
They check every current-build instruction/data guard and non-overlap, enforce
the source free-office flag conditional, and execute the generated unlock and
Mighty Sword and earned-JP Win64 code in an isolated synthetic Python
allocation. A further test executes the original native Fur Shop menu and
entry code without party abilities. These tests cover ordinary flags,
JP validity masks/team bits, protected/missing/synthetic equipment, accuracy
failure, damage factors, half damage, native helper targets and element input.
They do not launch or patch the game and do not establish gameplay validation.

Read-only inspection is reproducible with `research/qol_re.py <RVA>`, which
uses `.pdata` function boundaries and capstone. Relevant disassemblies are
saved under `research/qol-*.txt`.
