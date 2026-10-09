# Additional RCC native defaults

The adapter is `fftic/rcc_qol_extra.py`; its public entry point is
`apply_qol_extra(before, result, game_dir, flags)`. It appends six guarded
in-memory plans to `_RCCNativeTablePatches` and returns a JSON-compatible audit.
Default cleanup is independent of randomizer flags and RNG. The executable on
disk is never edited.

All RVAs below belong to `FFT_enhanced.exe` with SHA-256
`937233f7fe76182a665c487c8802f5cec6662ddd09967e87cd09fb146fc6b5d5`.
The adapter requires that hash plus exact bytes at each changed site. These
addresses must not be reused against another executable build.

## Proposition data cleanup

RCC `randomizer.py` lines 2889–2898 normalizes proposition unlock values 1–5
to 1 and doubles the eight proposition JP rewards. The verified native
aggregate header is at RVA `0x7B7650`. Its first offset is `0x3C`, and its JP
offset at header+`0x20` is `0xA70`.

| Native object | RVA | Verified layout / consumer |
| --- | --- | --- |
| Proposition table | `0x7B768C` | 96 records × 23 bytes; unlock byte at record+21; routine `0x2CCDC4` expands native records into ushort work data |
| Proposition JP table | `0x7B80C0` | Eight ushort rewards; reward routine `0x2D29C0` / `0x2D2B42` |

Unlock rows 0, 5, 10, 21, 23, 30, 50, 67 and 69 change from 5 to 1.
All other record bytes remain intact. JP rewards
`10,20,30,40,50,80,100,120` become `20,40,60,80,100,160,200,240`.

## Special characters on propositions

RCC `xml_patches/Razele.xml` lines 245–248 changes the generic-job cutoff
from 74 to 4 at original `WORLD_WLDCORE_BIN` offsets `0xCD9C` and `0xE834`.
This deliberately still excludes Ramza's source jobs 1–3.

The Enhanced world predicate is `0x2EE37C`, called by availability counting
at `0x2EDE98` and modern participant counting at `0x1A32DE`. It retains
the absent-name (`0xFF`), monster-flag (`0x20`), availability, and Enhanced
job 162/163 exclusions. Its cutoff instruction at `0x2EE3B1` changes
`83 FA 4A` to `83 FA 04`.

Do not apply this proposition cutoff of 4 to the superficially similar party
Rename predicates below. They serve different features: Rename must also
allow Ramza's jobs 1–3 and Enhanced special identities 162/163.

## Rename humans and special characters

RCC `Razele.xml` line 631 changes original `WORLD_WORLD_BIN` offset
`0x41205` from a shift-by-6 to a shift-by-22 on an unsigned actor byte.
This removes the original gender-based rejection. Its literal native
reference translation is retained by `legacy_rename_patches()` at `0x2850BD` in
`0x284F6C` roster mode 2, preserving unavailable flag 4. It is tested as a
reference but is **not installed by the default adapter**.

Enhanced uses native office mode 26 (`0x1A`) for **existing-party Rename**.
Its branch at `0x2EF575`–`0x2EF599` opens the existing party selector with
modern state `0x5EC`. The real `0x115FAC` resolver returns navigation type 6
for state `0x5EC`. The active navigation predicate in `0x2C0DB8` checks
availability at actor+`0x167`, unavailable flag 4 at actor+`0x70`, assignment
status, then the generic-only job gate. This gate excludes jobs below 74
and Enhanced special jobs 162/163.

The matching presentation predicate in `0x2C20F0`, type 3, also disables
these jobs. Its caller `0x2C2778` selects presentation type 3 specifically
when native list mode at `0x1848BB0` is 26. The office dispatcher commits
an existing party actor's UTF-8 name to actor+`0x126` at
`0x2EF142`–`0x2EF1C2`, then refreshes the party data. This is the active
consumer proof, rather than a guessed correspondence between UI names.

`rename_patches()` guards and bypasses only these two job-identity gates:

| Active gate | Guarded RVA / length | New branch target |
| --- | --- | --- |
| Existing-party navigation | `0x2C0F37`, 29 bytes | `0x2C0F54`, preserving the computed status/availability result |
| Existing-party presentation | `0x2C2217`, 26 bytes | `0x2C2330`, the available presentation state after earlier status checks |

Thus generic humans, unique humans including Ramza, and monsters retain
their native availability/status restrictions while all job identities can
be renamed. The UTF-8 dialog constructors and commit routines
`0x1B45EC` / `0x1B4AD8` add no later job/gender rejection.

The separate modern state `0x4BB` names **new recruit offers**, not existing
party actors. It uses worker mode 5 and confirms to `0x4BC` at
`0x12B39D`–`0x12B3B0`; its resolver returns navigation type 1. Office code
`0x336D5C` iterates its three generated recruits at compact-data offset
`0x178`. This flow cannot prove existing-party Rename eligibility. The
explicit navigation-type-3 cases in `0x115FAC` are states `0x457` and
`0x4B0`, not `0x4BB`. All three resolver results are exercised by the native
test. Also, `0x1004B4` always refreshes legacy roster mode 0; its 0–9
argument concerns bonus-item processing and is not a roster mode.

The unused legacy reference factory remains `legacy_rename_patches()`.

## Smart Encounters

RCC `xml_patches/Xifanie.xml` lines 1521–1535 changes the encounter chance
phase at original `WORLD_WLDCORE_BIN` offset `0x28188`: compare route
position `0x800D0B7C` with route length `0x800D0B80`. Eligible destinations
always select an encounter; passing nodes never select one.

The current native random encounter selector is `0x248BE4`–`0x248E06`.
Ordinary world travel `0x2482F8` calls it at `0x2485B7`, with `r8b=0`.
The travel loop increments native route position at `0x24845C` and compares
the route length at `0x24865D`:

| Native state | RVA |
| --- | --- |
| Route position | `0xD8DC08` |
| Route length | `0xD8DC0C` |
| Native encounter variance table | `0x7B69D0`, 19 areas × 3 entrances × 24 bytes |
| Selected encounter variant | `0xD494C8` |
| Xorshift128 RNG state | `0x8E5FC8`–`0x8E5FD4`, four uints |

The 125-byte chance block at `0x248CBF` is replaced in place by the route-end
comparison and branches. Passing nodes go to the original rejection return
at `0x248D3C`. Destinations go to `0x248D57`, which loads unchanged RNG state
for the native encounter-variant draw. Like RCC, the discarded chance RNG
draw is removed. The variant still consumes one native RNG draw.

Eligibility checks for map, entrance, chapter and a zero chance record remain
before the patch. The chapter variant mask and variant selection remain
native. Thus this does not create encounters on ineligible maps. Enhanced's
explicit battle selector at `0x2D134A` passes `r8b=1`, and its existing
`0x248CB6` bypass of the ordinary chance phase remains unchanged.

The source table's first area-24, entrance-1 record has first-chapter mask
`0xC0`; the bounded execution test verifies native encounter variant 157.

## Validation and limits

`tests/test_rcc_qol_extra.py` passes nine targeted tests on Windows. It checks
exact executable guards, no overlap with the base QoL plans, exact changed
table bytes, and changed-byte rejection. It also executes the reviewed
native Win64 proposition predicates, existing-party Rename job/availability
predicates, modern screen-profile dispatch and navigation branches, and the
full native encounter selector in allocated
test memory with synthetic actor/travel data. The real selector's chapter
getter is substituted at its original call target. Memory is released after
each test; no game process is started, attached to or modified.

This is stronger than a Python reimplementation comparison, but does not
claim an interactive Soldier Office/Tavern UI test or an in-game world-travel
test. Live loader validation remains the release pipeline's separate check.

Saved native evidence includes `research/qol-extra-unit-agent.txt`,
`research/qol-extra-current-eligibility.txt`,
`research/qol-extra-rename-input.txt`,
`research/qol-extra-unit-list-restrictions.txt`,
`research/qol-extra-modern-row-gates.txt`, and
`research/qol-extra-office-row-info.txt`. `research/qol_re.py` uses the exact
build's `.pdata` plus Capstone. Unwind fragments may omit cold code after a
return; branches must also be read across the full original function span.
