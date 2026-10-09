# RCC z special units, weather, map swaps and restored battles

The adapters use source version27, commit
`ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`. They mutate verified native data
without changing original archives or executables. Source control flow is
retained in `fftic/data/rcc-event-methods.py`, and ending/Warjilis unit-only
source fragments are embedded readably in the adapters. Python2 integer
division and list-returning range are restored when compiling these bodies.

## Source phases and APIs

The parent calls these in this order:

1. `apply_special_units` (RCC3881–4112): generates Balmafula/ArcWitch job33's
   stats and command124, then occasionally replaces anonymous enemy job/sprite
   groups with special-unit donor profiles. Named characters/allies stay
   protected; Lucavi and female-only scenes retain source exceptions.
2. `apply_ending_units` (RCC4285–4326,4356–4371): uses the same z RNG continuation
   to prepare Delita/Ovelia/Chocobo/Ramza ending records and funeral sprites.
   The parent owns the ending encounter, script and conditional program.
3. `guarantee_invite` (RCC5150–5154): if the ten source checked job skillsets
   have no ability116, force-add it to Ramza command27 using the source
   sixteen-slot behavior.
4. Parent generic-name changes, then `apply_weather` (RCC970–983,5157–5158),
   using the same z continuation. Weather changes are per native Encounter row;
   ENTD415/437/450 restore original weather/night after consuming source rolls.
5. With both z and f, `apply_map_surprises` (RCC5167–5177) resets a map-phase RNG,
   chooses a biased subset of eligible story encounters, and assigns each an
   unused source candidate map. The f phase then generates deployments and
   places units using the selected map and mover constraints.
6. After shops/items/music, `apply_warjilis` (RCC4415–4602,5218–5223) continues
   the preceding phase's RNG. It restores two battles on maps42/33 using
   ENTD476/477, one human and one monster roster, with a special allied partner.
   It allocates native encounter/formation rows and connects source predecessor
   encounters171 and449/450 to the new scenarios.
7. `apply_special_postmusic` (RCC5224–5228) gives Altima job65 command123 and
   enables postbattle recruitment for source ENTD402 slots1–7 and10.
8. `apply_alma_math_cleanup` (RCC5231–5236), independent of z: if Altima2 has
   secondary21, copy that command and unlock/job-level bytes to both Alma rows.
   Palette/recruit/Orbonne cleanup runs after this.

`UnitEngine.source_environment()` supplies shared unit objects/RNG/caches.
Special proxies add mutable job stats/commands, source gender constraints,
Invite immunity, most-common unit fields and complete table iteration.
`SurpriseWorld` extends `FormationEngine` locally with encounter copying,
unused-row allocation, music/weather and source map-candidate behavior.
All source methods operate on the same canonical rows; no independent
encounter database or runtime random roster is introduced.

`apply_special_units` stores the continuation environment in
`result['_RCCSpecialEnvironment']`. Ending, Invite and weather reuse it;
`apply_warjilis(...,environment=last_phase_environment)` must receive the
preceding phase's live RNG to preserve source phase continuation. It stores
`_RCCPostmusicEnvironment` for following parent event changes. Audits are
JSON-safe; environments remain private runtime objects.

## Native guards and metadata

The unit anchors are checked against immutable effective native input:
ending307 slots0–3 `(sprite,job,name)` are `(6,6,6)`, `(12,12,12)`,
`(130,94,255)`, `(3,3,3)`. Alma420slot0 is `(48,48,48)`, Alma441slot2 is
`(20,20,20)`, and Altima2 441slot8 is `(73,73,73)`. Source recruit402slot1
is `(130,151,119)` and402slot10 `(130,144,255)`.

Ending sets Unknown37/source unknown4 to0x400 on Ovelia/Chocobo; behavior8
on both and0x58/target3 on Delita, and Ramza's unit ID to3. Complete40-byte
records preserve these fields. Source status/equipment masks are little-endian
integers; the adapter converts from public native big-endian aggregates and
preserves FFTIC's additional fifth equipment permission byte.

Warjilis guards source clone encounter9 as map22/ENTD388; predecessor171 as
map43/ENTD282 and449/450 as map48/ENTD328. The highest original native scenario
is743, with713 active records. Restored battles occupy unused encounter indices
713/714 and get scenarios744/745. The original ending is encounter299,
scenario300, map45, ENTD307.

`nxd/eventid.nxd` has887 rows keyed0–886. Existing EventId744/745 are default
rows (DLCFlags0, Unknown4-1, union0:0, SeadState1) and remain unchanged. Blindly
copying EventId10 would copy its Enhanced event override Unknown4=10 and could
conflict with the selected legacy END event37.

`nxd/battle.nxd` has713 rows keyed by the active scenario IDs. New scenarios
744/745 require explicit complete rows copied from verified Battle10:
`{Key:744,DLCFlags:0}` and `{Key:745,DLCFlags:0}`. The world reader supplies
`_RCCBattleMetadata`; the adapter plans these in `_RCCWorldNexInserts['Battle']`.
The parent builder adds only these explicitly verified rows while preserving
every existing row and cell. Asset/Nex receipts keep the input hashes.

## Enhanced adaptations and boundaries

The literal surprise loop retains classic source ranges and appends the77
verified additional ENTD templates512–588. Donor eligibility, named/allied
protections and source probabilities remain intact. Map replacement also
allows extra native story encounters when verified terrain/mover data exists.
Map127 has no original RCC terrain mesh, so its map/deployment/coordinates are
preserved; this is reported in the audit rather than guessing geometry.

Full mode can move command27 to a parameter-based menu. When guaranteed Invite
is needed there, the adapter first copies an existing randomized human direct
action profile to27, sets its menu to0, preserves its R/S/M, and adds116.
`z_guaranteed_invite` records this adaptation, donor, old/new menu and action
count; the Full selected-owner audit reflects the final direct menu. RCC mode
retains the literal source injection behavior.

The parent owns the actual native ending script/conditional program, generic
name resources, WorldMap/SoldierOffice/auto-mash patches, and background END
patch/event37 resources for restored battles. The adapters do not copy PS1
absolute addresses into FFTIC. These resources and battle execution require
the separate final integration/runtime checks.

Targeted tests compare special units/Balmafula, weather and both human/monster
Warjilis table bodies directly with compiled source, including identical RNG
state. Native seed89 checks exercised all phases:143 surprise units,12 ending
records,424 weather rows,23 map replacements and32 restored-battle units.
The original archives remained untouched.
