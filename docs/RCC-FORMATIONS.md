# RCC formation phase on Enhanced FFTIC

`fftic/rcc_formations.py` adapts RCC's `f` phase using the literal
`generate_formations` and `randomize_enemy_formations` function bodies bundled
in `fftic/data/rcc-event-methods.py`. The source is RCC v27 commit
`ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`, originally
`randomizer.py:735-972`, `4114-4273` and the top-level f loop at5175-5195.
The data importer records the source provenance; the generated seed does not
need the user's old randomizer checkout.

Python2 integer division and list-valued zip/range are preserved. The source
sorts a set containing numeric heights and None before removing None; the
adapter retains Python2's None-before-number order. Its unreachable interactive
debugger becomes a normal diagnostic for an invalid terrain rectangle. No
generation probabilities or normal mutation widths are replaced.

## Native records

Verified Enhanced executable SHA256:
`937233f7fe76182a665c487c8802f5cec6662ddd09967e87cd09fb146fc6b5d5`.

| Table | File offset | RVA | Stride | Capacity |
|---|---|---|---:|---:|
| Encounter | `0x8EAEB0` | `0x8ECAB0` |24 |887 |
| Formation | `0x7AC6D0` | `0x7AE2D0` |12 |768 |

Encounter rows preserve scenario, weather, night, music, ENTD, grid/grid2,
unknown fields, Ramza, next scene, following and event fields. The f phase
changes only grid/grid2. Formation records are packed as little-endian
`<IBBBBBBH`: bitmap, x, z, zero, orientation, num_characters, map_number,
id_number. All native IdNumber values equal their row index.

The original input has104 eligible encounters (`map_id`, `entd`, `event` and
`grid` all nonzero),537 used formation records and231 available nonzero-index
empty records. Source allocation takes the highest-index unused formation,
then proceeds downward. This native capacity can accommodate two formations
per eligible encounter. Existing nonempty formations are preserved: the f
loop invokes `FormationObject.mutate()` with its default reduction flag off,
which is a source no-op.

Deployment masks retain the source column-major5×5 bitmap packing, x/z center
offset of2, one-or-two-region probabilities, character-count split, terrain
certainty across map variants, height/depth rules, region collision conditions,
occupied tile constraints and facing/orientation selection. Valid deployment
tiles become party/occupied tiles in the private terrain model only; terrain
meshes are not modified by f.

## Maps, units and script constraints

`_RCCMaps` contains121 original terrain maps. The source map object selects
the first eligible encounter with the matching map ID; it does not change its
unit owner to the encounter currently being processed. The adapter preserves
that selection and map variant0 for enemy placement. Formation validity uses
certainty values across all variants. Initial scripted movement destinations
come from the bundled `rcc-map-movements.txt`; current positions of moving
native ENTD units are marked occupied as well.

Source mover classification uses sprite/graphic values. A scripted generic
sprite marker excludes all generic sprites from nonmoving units; explicit
scripted sprite IDs are excluded individually. Ordinary maps reposition only
nonmoving units. Replaced maps reposition every unit and suppress upper-layer
placement, matching the source's encounter `mutated` branch.

The heatmap retains source bad-terrain handling, occupied coordinates, edge
penalties, adjacent/opposing-team distance weights, party-region distance
weights, rank trimming, chosen coordinates, facing and upper-layer odds.
The original tile accessor is a flat256-tile array. The proxy preserves its
row-wrap behavior for out-of-width neighbor probes. Inactive padding tiles
have no generated party flags, as in the source initialization.

Cloning uses the highest-index completely unused unit (`graphic==0` and
`job==0`). Its threshold is the exact
`min(int(60*((0.5*difficulty_factor)**new_unit_count)),60)` rule. At least six
unused slots are required before adding a unit, leaving the original five-slot
reserve. Source donor exclusions, job-diversity preference, full40-byte copy,
`mutate(preserve_job=True)`, restored unlock level, presence flags, unit ID,
unnamed marker, friendly/recruitable/alternate-team odds and collision retry
are retained. Final unit palette cleanup belongs to the shared UnitEngine's
source cleanup phase after all encounter changes; f does not invent a separate
palette rule.

The only supported-input terrain exception is native encounter506, scenario537,
ENTD519 on map127. FFTIC has no original RCC terrain mesh for that map. Its
deployment grids and coordinates remain unchanged by f, and the audit records
the exact encounter and reason. Other missing eligible original terrain fails
explicitly; it is not silently skipped.

## Integration

Call:

```python
audit = apply_formations(before, result, seed, chaos=1,
                         random_degree=.25, degree=1)
```

The phase modifies `_RCCEncounters`, `_RCCFormations` and shared
`_RCCUnitContext` rows; it writes no files. The parent commits world table
changes through the guarded native patch module and ENTD changes through the
existing native asset/Nex reconciliation. `_RCCReplacedMaps` must contain the
indices of encounters whose map was replaced before f. `_RCCUnitEngine` is
reused when available, preserving canonical row references and cached source
state. Its partial u selection mask is temporarily cleared so f's independent
clone mutation is not suppressed.

The JSON audit lists selected/generated/changed encounters, newly allocated
formation records, changed units, added unit owners, terrain inventory and
unsupported encounters. `FormationEngine` also exposes row-backed native map,
encounter and formation proxies, source-compatible MapObject/EncounterObject/
FormationObject bindings and the literal function environment for other
authorized source event phases.

## Validation

`tests/test_rcc_formations.py` compares the adapters with functions and property
bodies compiled directly from the user-provided original RCC checkout. It
checks all121 maps initialize with scripted movers,768-record allocation,
orientation and complete RNG state, certainty across variants, column-major
deployment masks, complete enemy heatmap/cloning outputs and RNG state,
five-slot reserve, mover selection, map127 preservation and explicit failures
for missing original terrain. Offline parity checks do not replace the final
packaged seed's loader/game validation.
