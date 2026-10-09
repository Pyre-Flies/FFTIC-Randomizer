# RCC Nex output and reconciliation

`fftic/preview.py:build_rcc_nex` merges the verified original Nex databases,
applies authorized sparse changes and rebuilds tables with the bundled
FF16Tools CLI. It converts the resulting files back to SQLite and compares
every row key and cell, including unrelated rows and columns.

The preview cache supplies localized Ability tables, OverrideAbilityActionData
and, for selected Full-mode owners, localized JobCommand labels. The world
cache supplies GeneralJob, seven localized PoachItem tables, Battle,
EnhancedBattleEvent, EnhancedWorldEvent and CharaControlId. The
unit context cache supplies OverrideEntryData. Original table SQL and rows
are copied without changing column order or converter union type metadata;
incompatible metadata or conflicting duplicate baselines fail explicitly.
Source database SHA256 receipts are checked before merging.

World cache format `world-r-t-v3-conditionals` includes original battle.nxd
and both Enhanced conditional tables plus their character control aliases.
`prepare_world_data` exposes `_RCCBattleMetadata` and validates its complete
schema is exactly Key/DLCFlags. This is required for the source historical
battle additions; prior world caches remain intact and are not reused for the
new format.

## Allowed changes

| Family | Keys | Allowed output fields |
|---|---|---|
| Ability locales | Key | JpCost1, JpCost2 |
| OverrideAbilityActionData | Key | Range, EffectArea, Vertical, Element, Formula, X, Y, InflictStatus, CT, MPCost, Flags12, Flags34 |
| JobCommand locales | Key | Name, Description, Description2 for selected Full owners |
| GeneralJob | Key | RequiredJobExp, RequiredJobIds, RequiredJobLevels, RequiredJobPositions |
| PoachItem locales | Key | Unknown2C, Cost, SellPrice, Unknown18 |
| CharaName locales | Key | Name |
| OverrideEntryData | Key + Key2 | Verified NEX_FIELDS plus InitialDirection/HigherElevation reconciliation and Disable |
| Battle | Key | Only complete new historical scenario rows744 and745 |
| Enhanced conditional tables | Key + Key2 + Key3 | Complete guarded authored clause replacements; see RCC-CONDITIONALS.md |

All ordinary updates must address exactly one existing original row. Compound
keys are bound together, so changing ENTD387/slot0 cannot also change slot1.
Arrays are stored as JSON lists. The roundtrip compares every array element;
SQLite's JSON whitespace is immaterial. Other scalar/text cells compare
exactly. Undeclared columns, changed row keys, duplicate keys, missing targets,
unexpected inserted/deleted rows and converter value changes are rejected.
All SQLite connections close explicitly, including failure paths.

`_RCCAdditionalNexSources` supplies hash-verified original sources such as
the seven CharaName tables. Only requested tables are imported. Poach Cost
and SellPrice updates reconcile source randomized reward/price behavior
with Enhanced's fixed shop UI values; Unknown18 is the localized reward
description. Conditional group replacements are a separate checked plan,
recomputed from the source delta before changing any complete rows.

The final `_RCCMetadataUpdates` JP state takes precedence over earlier JP
audits. This includes source forced costs after later monster/event phases.
Status-phase y action fields merge after a, so the final InflictStatus is
retained along with prior CT/MP/range/flag changes. Optional b testing costs
are applied last using the established seeded player-action selection rule.
Full-mode label changes retain native icons/dialog/other command fields and
use the existing localized profile labels or translated generic label.

## Historical Battle insertions

The verified native encounter inventory ends at scenario743. The source
Warjilis additions use new scenarios744 and745. EventId already contains valid
default records for those IDs, so it receives no invented rows or fields.
Battle lacks744/745 and requires exactly these rows:

```json
{"Key":744,"DLCFlags":0}
{"Key":745,"DLCFlags":0}
```

Each is a complete copy of verified Battle10 with its new Key. The builder
checks the original maximum scenario, source template, full schema, unused
keys and exact requested fields. `_RCCWorldNexInserts` may contain only these
Battle rows. The rebuilt table must preserve every original row and add
precisely the declared rows with the declared complete values.

Sparse ENTD overrides are different: an owner absent from OverrideEntryData
requires native ENTD asset output only. No default override row is invented.
For an existing override, the known fields that could mask changed native
values are reconciled. Direction/elevation and Disable updates likewise require
an existing source override row. This preserves the original516-row override
inventory, including FFTIC's extra ENTD519 which has no override rows.

## Validation

`tests/test_rcc_nex.py` exercises compound-key isolation, unrelated-cell
rejection, JSON array roundtrips, row inventory guards and strict historical
insertion validation. Its real FF16Tools test rebuilds25 tables together:
seven Ability locales, action overrides, seven JobCommand locales,
GeneralJob, seven PoachItem locales, two-key entry overrides and Battle.
All rows/cells match the intended complete databases; only the two verified
Battle rows extend the baseline inventory. Reports use list-valued compound
keys and remain JSON serializable. Loader/runtime validation remains the
parent's responsibility for the final seed package.
