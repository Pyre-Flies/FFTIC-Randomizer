# RCC encounter units on Enhanced FFTIC

The `u` phase adapts RCC version27, source commit
`ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`, `randomizer.py` UnitObject
2083–2745 and mutate_units3820–3878. These are seeded, offline mutations of
encounter templates. Revisiting a battle does not generate a new randomizer
seed or roster. Native random-presence, normalized levels and automatic
equipment still operate at runtime.

`fftic/rcc_encounter_data.py` reads the original assets without editing them.
`fftic/rcc_units.py` uses literal source control flow with per-engine RNG/state,
Python3 syntax and Python2 integer-division semantics. The adapter covers
random and story templates, named-job/birthday consistency, sprite budgets,
job requirements and JP budgets, monster species, secondary commands, R/S/M,
equipment sentinels, sword/Materia Blade compatibility, levels and Brave/Faith.

## Verified inputs

Supported Enhanced executable SHA256:
`937233f7fe76182a665c487c8802f5cec6662ddd09967e87cd09fb146fc6b5d5`.
The archive-keyed read-only extraction cache is
`research/rcc-context/dbca126751c1e768` for this installation.

| Archive | Asset | Shape | ENTD IDs |
| --- | --- | --- | --- |
| enhanced/0002.pac | fftpack/battle_entd1_ent.bin |128×16×40bytes|0–127|
| enhanced/0002.pac | fftpack/battle_entd2_ent.bin |128×16×40bytes|128–255|
| enhanced/0002.pac | fftpack/battle_entd3_ent.bin |128×16×40bytes|256–383|
| enhanced/0002.pac | fftpack/battle_entd4_ent.bin |128×16×40bytes|384–511|
| enhanced/0002.pac | fftpack/event_btlevt_bin_entrydata_add_ent.bin |77×16×40bytes|512–588|
| enhanced/0004.pac | nxd/overrideentrydata.nxd |516sparse rows|effective existing fields|
| enhanced/0004.pac | nxd/generaljob.nxd |21rows|native progression|

The four original binary hashes and both Nex hashes are recorded in the cache
receipt. The fifth asset is extracted and added to that same integrity receipt.
All589 templates and9,424 unit records are decoded, including405 occupied
extra records. Native active scenario rows use extra ENTD512–529,533,550–585;
519slot0 is native Templar/job165 and following monster slots use job154.
This confirms the additional file's base512 mapping independently of size.

The original opening anchor ENTD387slot0 has Spriteset2, MainJob2 and UnitId2;
the same template contains Agrias job52 and generic Knights job76. The source
recruit anchors are verified by original sprite/name/job triples before use:
405slot1 `(12,12,12)`,413slot0 `(30,30,30)`,417slot0 `(21,21,21)`,
428slot0 `(25,25,25)`,433slot0 `(41,41,41)`.

## Native unit layout

Offsets are within a40-byte record; multibyte integers are little-endian.
The full record is modeled so copying an enemy also copies the final fields.

| Offset | Bytes | Canonical field/source alias |
| --- | --- | --- |
|0|1|Spriteset/graphic|
|1|1|Flags1/misc1|
|2|1|NameId/name|
|3|1|Level/level|
|4–7|1each|BirthMonth,BirthDay,Bravery,Faith|
|8–11|1each|JobUnlock,JobLevel,MainJob,SecondarySkillset|
|12,14,16|2each|Reaction,Support,Movement|
|18–23|1each|Head,Body,Accessory,RightHand,LeftHand,Palette|
|24|1|Flags2/misc2|
|25–27|1each|PositionX,PositionY,InitialDirection|
|28–29|2|Unknown28+EntryUnknown1D/source unknown2|
|30–32|1each|TrophyItemId,Gil,UnitId|
|33–34|2|Unknown33/source unknown3|
|35–36|1each|Behavior,TargetId|
|37–39|3|Unknown37/source unknown4|

RCC table bit definitions are LSB-first. Flags1 bits0–7:
save_formation,test_teta,hidden_stats,load_formation,join_after_event,monster,
female,male. Flags2 bits0–7: z1,z2,immortal,control,enemy_team,alternate_team,
randomly_present,always_present. InitialDirection bit7 selects elevation.
Public JobData status masks use big-endian aggregates; RCC ranking constants
use little-endian interpretation of the same five bytes. Ranking converts
those byte orders before testing crippled status.

Effective overrides follow verified sentinels: negative optional scalar leaves
the native value; Spriteset/MainJob/Level/JobLevel apply positive values;
JobUnlock20 preserves native; direction255 preserves native; HigherElevation
0/1 updates bit7; Disable zeroes the sprite; LoadFormation enables its bit.
Unmapped Nex Present, UnitId+characontrolid+Id, Unknown4, and skill arrays
Unknown4C/54/5C/64/6C/74 are retained. Names alone are insufficient to map them
to ENTD bytes.

## Ordering and integration API

Prepare unit context before phases. `native_rankings(before)` reproduces the
baseline make_rankings inference, cached before mutation as RCC5086 requires.
Current skillsets/action flags and JP costs are read after their phases for
sword compatibility and secondary suitability.

The requirements phase calls
`prepare_unit_backups(before,result,rng,random_degree=.25)` after mutating the
eight JP thresholds and before changing the job tree. It consumes that same
requirements RNG and uses original requirement closure with new thresholds,
matching RCC5094–5096. The native curve starts100,200,400,700,1100,1600,2200,3000;
GeneralJob's extra leading zero is removed.

`apply_job_unit_overrides(result,overrides)` applies innate/Lucavi RSM writes
before `u`. `apply_units(before,result,seed,flags,degree=1,chaos=1,
random_degree=.25)` returns a JSON-safe audit and retains the live adapter in
`result['_RCCUnitEngine']` for formation/surprise work. Lower degree selects
whole encounter templates to preserve sprite budgets; degree0 is an exact
no-op. `UnitEngine(before,result,rng,...)`
can also be created independently when formation/surprise flags run without u.

After all units/formation/surprise/trophy work,
`finalize_cleanup(...,rng=last_phase_rng)` performs palette cleanup using the
last phase's RNG, then resets its recruit seed and normalizes the verified five
recruits and gives Orbonne387 allies control, matching RCC5239–5260.
The parent handles Soldier Office and all event/assembly changes.

`commit_unit_assets(before,result)` performs one final diff against pristine
effective input. It publishes replacement bytes as `_RCCEntryAssets`, sparse
existing Nex cell changes as `_RCCEntryNexUpdates`, and field audit as
`_RCCEntryChanges`. It starts each record from untouched native bytes and
patches only changed canonical fields. It does not bake all existing Nex
overrides into assets. Existing Nex cells that would override a changed byte
are updated as part of the same generated package. The parent serializes these
assets through the existing archive override path; original game assets stay
unchanged.

## Enhanced adaptations

Ordinary job74–93 mapping is independently anchored by game.py. Creature
pool identity uses native traits; the unit species list preserves RCC's classic
94+ species and Lucavi151 exception, plus real added native species. Unique
creature-shaped classic jobs60–73 retain RCC unique-unit equipment/secondary
handling. Boco's classic list is extended only by real native added species.
Additional ENTD512–588 gets the same applicable unit and monster-family rules.
Baseline ranking inference includes these native extra story templates.

Two verified extra-table cases need explicit native adaptation. ENTD516slot4
is an inactive placeholder with MainJob0, JobUnlock169 and no presence flags;
its invalid generic unlock is preserved and its initial JP budget is0.
ENTD521 repeats Alicia/Lavian using a shared native Knight sprite; established
global named-job mappings can need distinct sprites. That extra-template case
spends unused capacity within the original nine-sprite limit instead of
discarding character consistency. The original512 templates retain source
budget rules unchanged.

Unit reference tests compare statistics/birthdays/levels, equipment/sword/RSM,
and progression/secondary methods with functions compiled directly from the
user's RCC checkout, including identical RNG state. Additional tests cover
all40bytes, full-record copies, extra-asset emission and native degree0.
These checks establish data and algorithm behavior; battle execution and the
fresh Reloaded-II log are separate final integration checks.
