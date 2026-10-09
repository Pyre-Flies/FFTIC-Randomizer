# RCC innate, status and metadata parity

The implementation is in `fftic/rcc_innates.py`, `fftic/rcc_status.py` and
`fftic/rcc_stats.py`. The reference is the user-provided RCC v27 checkout,
commit `ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`, principally
`randomizer.py:1938-2090`, `1343-1367`, `1452-1489`, `3529-3585`,
`3726-3737` and `3809-3819`. Its original helper distributions are retained.

The source `i` rule mutates equipment permissions, optionally mutates elemental
relationships, mutates statuses and chooses innates. Squire/job74 returns after
the first two steps; its four innates and statuses remain unchanged. The four
ordinary innate slots have RCC's original 1-in-20 replacement trigger; source
monster jobs have the original greater-than-10 trigger on the same 1..20 draw.
New support innates use the original additional coin flip and JP-ranked
midpoint distribution. Types7/8/9 come from the native metadata rather than the
localized learned-ability eligibility filter; RCC does not filter these by
name or its learned-passive ban list.

Lucavi jobs60,62,64,65,67,69,73,151 use the source whitelist and sampling loops.
They receive six distinct reaction/support abilities: four job innates and two
native encounter-unit fields. The movement choice retains the source MP-restoration
constraints. Altima/job65 receives movement499. Every native encounter unit
whose MainJob equals the affected job must receive the explicit returned
Reaction/Support/Movement override before the unit randomization phase.

The original iterators are numeric, not actor classifications: `i` visits all
classic job rows0..93, and `m` visits94..159, including otherwise unused rows.
There is no no-command or zero-stat exclusion in the source. The port follows
those bounds. Populated FFTIC-only jobs160+ are added to the corresponding
iterator using verified native creature traits; their innate probability uses
that actor classification. Unpopulated additional rows have no invented rule.
FFTIC's fifth equipment-permission byte is preserved while the original four
bytes use the exact RCC rule. Active Enhanced JP values are read from its Nex
catalog for innate ranking; explicit earlier phase updates take precedence.
Source `get_abilities()` forces ability499's JP to9999, and that update is
included in the metadata and localized JP output even when `j` is disabled.

The source `m` phase interleaves each monster job's stats and innates, then
mutates the four-slot monster commands using the continuing RNG. The helper
`apply_monster_stats_innates(..., rng=shared_rng)` exposes this ordering; pass
the same RNG onward to `apply_monsters(..., rng=shared_rng)`. Human `j` similarly
uses one continuing RNG for job stats followed by command JP/learn rates.
Computed learn chances are emitted as native metadata updates, rather than
only consuming their RNG draws. Zero-valued classic stat records participate
in the original clamp-to1 and mutation rules.

The source `y` phase initializes exactly option rows29..31 and122..127, mutates
all effective action status infliction fields, then mutates weapon options,
using one RNG. It preserves the original Toad/ability29 exclusion, conditional
Crystal96 area/Arithmeticks/three-direction exclusion, and status-option
operation precedence when correcting existing add/cancel AI behavior. Weapon
cast formulas remain governed by the original weapon rule. Item equipment
bonus status/element mutation remains inactive because RCC comments it out.

## Verified native fields and endian boundary

Enhanced executable SHA256:
`937233f7fe76182a665c487c8802f5cec6662ddd09967e87cd09fb146fc6b5d5`.
Pinned loader source commit:
`c74047dc1b36bfe1bf6a466cf3645f1fe9815425`.

JobData has174 rows, stride49, file offset`0x784230`, RVA`0x785E30`.

| Public field | Native row bytes | Representation |
|---|---:|---|
| InnateAbilityId1..4 | 1..8 | Four little-endian uint16 values |
| EquippableItems | 9..13 | Loader big-endian40-bit enum |
| InnateStatus | 27..31 | Loader big-endian40-bit enum |
| ImmuneStatus | 32..36 | Loader big-endian40-bit enum |
| StartingStatus | 37..41 | Loader big-endian40-bit enum |
| AbsorbElements, NullifyElements, HalveElements, WeakElements | 42..45 | Four byte masks |

RCC's TableReader interprets multibyte integer fields as little-endian. Its
status constants therefore cannot be applied directly to the loader enum
integer. The port swaps five-byte integer order before applying source masks
and swaps back afterward. For example RCC Faith`0x8000000000` maps to native
enum`0x80`; the source's Reraise`0x0000200000` maps to native`0x200000`.
Equipment permissions likewise swap their original four bytes before mutation.
The `rcc_context.py` crippled-job rank test also converts native status masks
before using the RCC valid-status constant.

ItemOptionsData has128 rows, stride6: OptionType is byte0 and Effects is the
loader big-endian40-bit aggregate of bytes1..5. OptionType operations are
Cancel`0x10`, Separate`0x20`, Random`0x40`, AllOrNothing`0x80`.
The verified Enhanced file offset is`0x80DFA0`, RVA`0x80FBA0`.
The pinned loader's `Signatures/ffto.ini` anchor is:

```
10 00 00 00 80 00 10 00 20 00 00 00 10 00 08 00 00 00 10 00 00 02 00 00 10 00 80 00 00 00
```

Effective AbilityAttributes has368 rows, native stride20. Status infliction is
byte11; EffectArea is byte1; three-direction flag is Flags2`0x02`; Arithmeticks
eligibility is Flags3`0x40`. Existing Enhanced Nex action overrides are applied
before either `a` or `y`, and the final infliction result must be merged into
the Nex action update audit after `y`.

AbilityMetadata has512 rows, stride8, file offset`0x786380`, RVA`0x787F80`:

| Private field | Native bytes | Representation |
|---|---:|---|
| JPCost | 0..1 | uint16 little-endian |
| LearnChance (loader ChanceToLearn) | 2 | byte |
| Flags and AbilityType | 3 | Upper/lower nibble respectively |
| AIBehaviorFlags | 4..7 | uint32 little-endian |

Status AI AddStatus is`1<<4`, CancelStatus is`1<<5`. The AI mask is treated as
uint32 even though the loader enum underlying type is signed int32.

## AbilityData loader bug and emission path

The installed loader version1.7.5 main DLL SHA256 was
`0c497071346f52ed03953389f7362427e0b5272a36b39260055e800889457580`.
`FFTOAbilityDataManager.ApplyTablePatch` writes byte3 with the source expression:

```
(((byte)abilityFlags & 15) << 4) | ((byte)abilityFlags & 15)
```

The lower nibble should use AbilityType, so even an XML patch changing only
ChanceToLearn or AIBehaviorFlags can corrupt that row's type. The installed
DLL was inspected read-only with Mono.Cecil: the second `ldloc.1` at IL`00AD`
feeds the lower nibble; `00B3` calls the native Flags setter. This confirms the
same defect in the binary rather than only in the pinned source checkout.
Mono.Cecil is available offline under
`%USERPROFILE%\.nuget\packages\microsoft.net.illink.tasks\10.0.12\tools\net\Mono.Cecil.dll`.

The seed therefore emits no AbilityData XML. The generator exposes
`_RCCMetadataUpdates` and mutated `_AbilityMetadata`, and the parent native
patch module writes only JPCost, LearnChance and AIBehaviorFlags at the verified
table location with executable-hash and expected-original-byte guards.
Byte3 is preserved. `metadata_updates()` explicitly rejects any type or flags
change and validates the native integer widths. Localized JP Nex fields are
also updated because Enhanced displays those overrides rather than raw
metadata JP. No installed loader binary needs modification.

## Validation evidence

`tests/test_rcc_innates_status.py` extracts the original Python2 function bodies
from the user's legal source checkout and compiles them with minimal Python3
syntax/runtime adaptations. Tests compare values and complete RNG state for
every innate branch, source status options, full options→action AI→weapon
ordering, interleaved monster stats/innates, and emitted JP/learn rates.
It also checks endian semantics, Squire exemption, disabled/zero-degree rules,
and preservation of the native type/flags byte. These are offline source
parity checks; runtime loading and in-game behavior require the parent's live
validation of the final packaged seed.
