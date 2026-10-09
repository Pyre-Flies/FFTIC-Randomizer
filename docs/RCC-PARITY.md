# RCC v27 feature parity in FFTIC Enhanced

Source: abyssonym/rumble_chaos_crashdown commit
`ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`. The port follows the effective
source algorithms and active defaults, not comments alone. Full redistribution
is an additional custom allocator. Numeric PS1 seed equivalence is not claimed:
the Python3 generator uses reproducible phase-hashed streams and Enhanced data.
At source-default settings, the port preserves source mutation/transfer rules
and draw ordering within the documented Enhanced adaptations. Additional data,
phase seed derivation and optional degree/count controls change exact outcomes.
Continuations after the final active phase and the f deployment reseed are
explicit.

| Source feature | Enhanced adapter / evidence |
| --- | --- |
| r JP curve, backup JP and prerequisite tree | rcc_requirements.py; RCC-WORLD.md; literal source/RNG comparisons. |
| i human job innates and permissions | rcc_innates.py; RCC-INNATES.md. |
| s normal + unique skillsets | rcc.py; source comparisons and shared command ownership. |
| a action attributes | rcc_actions.py; effective native + Nex inputs. |
| y option/status/AI/weapon chain | rcc_status.py; same continuing stream, preserved native type/flags. |
| j stats, JP and learning | rcc_stats.py; source stats→cost/learn ordering. |
| m interleaved monster stats/innates and skills | rcc_stats.py + rcc.py; shared monster stream. |
| u allies/enemies/species/equipment/presence | rcc_units.py + rcc_encounter_data.py; RCC-UNITS.md. |
| z specials, ending, names, weather, map changes, restored encounters | rcc_specials.py, rcc_names.py, rcc_surprises_world.py; RCC-SPECIALS.md. |
| f deployment regions, formations and enemy heatmap/clones | rcc_formations.py + rcc_maps.py; RCC-FORMATIONS.md. |
| t unit rewards, poach and move-find | rcc_rewards.py; RCC-WORLD.md. |
| p/w shop and item rules | rcc_equipment.py; direct source comparisons. |
| c music bans, unused candidates and resets | rcc_music.py; direct source/RNG comparisons. |
| o dialogue flags | rcc_events.py; verified Enhanced operand decoder, source byte mask. |
| Overworld and conditional changes | rcc_events.py + rcc_conditionals.py; RCC-CONDITIONALS.md. |
| Final unit cleanup, recruit normalization, Orbonne controls and Alma Math fix | rcc_units.py + rcc_specials.py; effective source cleanup order. |
| Fiesta and Easy Mode | rcc_secrets.py + guarded native Fiesta helper; RCC-SECRETS.md. |
| Eight active patches.cfg defaults | rcc_qol.py + rcc_qol_extra.py; RCC-QOL.md. |

This map covers the implemented phases, eight enabled patches.cfg entries,
built-in changes and the two secret codes. The commented optional XML patch
catalog is not part of the current feature-parity claim. Full redistribution
and the six free testing actions are custom features.

## Emission and ownership

The generator reads the supported original executable/archives. XML contains
sparse supported table changes. Effective encounter overrides are reconciled
only for existing Nex owners; raw40-byte ENTD records preserve unknown bytes.
Four original ENTD files plus the Enhanced additional ENTD file cover589
templates/9424 slots. New restored scenarios use unused native Encounter
capacity and complete Battle metadata rows744/745 cloned from the verified
baseline. Formation records retain their native768-row inventory.

Localized JP/commands/names/poaches, requirements, entry overrides and native
conditional tables are rebuilt through FF16Tools. Every output table is
roundtripped with exact schemas, compound keys, all cells and array elements.
Conditional changes use guarded complete clause replacement, retain modern
routes/aliases and check native interpreter capacities.

Missing native table/code support is supplied by the project's own startup
bridge and runtime DLL. The managed bridge runs after the signature scanner
and Nenkai's pack/XML finalization through Reloaded's synchronous initialized
callback. The runtime preflights the exact executable hash and all expected bytes, checks
overlaps/ranges, obtains protections before any write, then applies in-memory
changes. No installed loader binary or original game file is modified.

## Explicit adaptations

- Additional real Enhanced jobs and encounter templates participate according
  to their verified actor identity. Native unused ability IDs cannot enter
  newly assigned lists. Shared IDs remain authoritative.
- The native map127 encounter506/ENTD519 has no original RCC terrain mesh;
  f preserves its deployment grids/positions and names it in the audit. Other
  missing eligible original terrain is an error.
- Move-find coordinates must fit packed4-bit axes. Terrain dimensions17/18
  are sampled with out-of-range coordinates rejected. Enhanced unit gil has
  a native byte bound, so larger rounded source rewards are clamped.
- Poach keys follow Enhanced carcass order, matched by original monster IconId.
  Reward IDs are changed in all seven locales. Fixed carcass buy/sell prices
  follow the final reward item price; descriptions naming replaced rewards
  are replaced with localized randomizer text.
- Enhanced conditional clauses contain new guards and character aliases. The
  port changes verified corresponding source guards, adds source fallback
  clauses and retains unrelated modern routes. The ending's old variable128
  maps to native509 only in its anchored ending context.
- Enhanced dialogue operand lengths differ. Source custom Murond bytecode is
  translated to native message IDs; ending/progression cuts use decoded scene
  boundaries. Raw PS1 executable/disc offsets are never applied to Enhanced.
- Ability metadata JP/learn/AI changes use the native runtime to preserve the
  type/flags byte affected by the upstream AbilityData XML manager defect.
- Poach-free shop entry is already native Enhanced behavior; original native
  menu/controller code has been tested without party ability data.
- Full mode's guaranteed-Invite z injection can adapt Ramza's command27 to a
  compatible direct-action menu and add an action after its configured count,
  bounded by the native16-slot limit. RCC source guarantees Invite globally.
- Optional Fiesta preserves source quirks: its last-slot Stone Gun write and
  the effective overwritten raw Mime requirement patch. Fiesta precedes Easy
  Mode after cleanup, with no invented subsequent cleanup.

## Verification limits

Source comparisons, real installed-serializer checks, exact generated Nex
roundtrips and startup/readback validation are distinct evidence. A clean
startup log does not prove battle completion, every ability/sprite pairing,
shop interactions or campaign progression. Those require gameplay fixtures.
Final validation evidence is recorded under research/live-validation-0.6.0.
The corrected post-loader bridge launch found AbilityData/SpawnData normally,
applied all 23 native ranges and passed readback of all 14 XML tables, all 34 Nex
tables and all 15 merged binary/script assets. No errors or conflicts appeared.
The pre-existing CFILE_DAT__Decode warning remains with DecodeAlt matched.
The game responded for 69.6 seconds and closed gracefully; all 37 original EXE/
numbered archive hashes stayed unchanged. No gameplay input was performed.
The earlier scan-warning audit is preserved separately under
research/live-validation-0.6.0-before-startup-bridge.

Version0.6.1 additionally reads the Enhanced extended-item metadata privately
so Materia Blade+ at buried slot75/4 can guide RCC replacement ranking. Original
byte-sized candidate pools remain unchanged. The exact reported seedf6745fb4
(RCC,50% randomness,Fiesta) passed11 focused checks and real loader/readback of
24 native ranges,13 XML tables,27 Nex tables and15 assets. Evidence:
research/live-validation-0.6.1-f6745fb4. The previous Full installation and its
eight overlay packs were then restored and hash-compared with their backups.
