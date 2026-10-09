# RCC conditional tables on Enhanced FFTIC

`fftic/rcc_conditionals.py` ports the authored conditional changes from RCC
v27 (`ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`). It consumes no random
numbers. `apply_conditionals(before, result, flags='', world=True)` always
applies the source overworld progression changes unless explicitly disabled;
flag `z` also applies the source ending's battle conditional table.

The importer `tools/import_rcc_conditionals.py` compares the original legal
game tables against the authored source `.dat` files and stores parsed
before/after programs for changed first-level groups only. The distributed
JSON contains structured source edits and anchors, not executable overlays,
disc-relative patches or raw game tables. Original assets stay in the local
research cache. Source hashes and original asset hashes are recorded in
`fftic/data/rcc-conditionals.json`.

## Verified format and native consumers

Both old tables have two levels of little-endian ushort pointers. The first
word is the byte size of the first-level TOC: battle `0x124` has146 entries;
world `0x58` has44. Each first-level entry points to a zero-terminated list of
program pointers. Programs use fixed-arity ushort opcodes and operands. For
example, battle `[1,509,1,25,2]` is a variable comparison followed by event2,
not an opcode with a count-prefixed list. World `[1,110,32,25,223,2]` compares
variable110 to32 and dispatches event223 with its second operand2.

The original native battle overlay's table starts at file offset `0x14938`
in `fftpack/overlay/event_attack_out.en.bin`; its first program is `0x538`
relative to the table. The native world table starts at file offset `0x30234`
in `fftpack/world_wldcore_bin.en.bin`. The authored world file is3701 bytes,
ending on the low byte of a ushort. The original source writes it in place,
leaving the following original high byte intact. The importer reproduces
that write before decoding, rather than discarding or inventing the byte.

Verified Enhanced executable SHA256:
`937233f7fe76182a665c487c8802f5cec6662ddd09967e87cd09fb146fc6b5d5`.

| Consumer | Verified evidence |
|---|---|
| Battle scenario loader | RVA `0x2FB7C8` through `0x2FC484`; Nex table ID `0xA3` |
| Battle buffer limits | Sixteen clause pointers and512 ushort program words; loader rejects total reaching512 |
| Battle unit control lookup | RVA `0x2FC26F` through `0x2FC2EA`; Nex table ID `0xDA`, CharaControlId.Unknown8 byte |
| World conditional loader | RVA `0x343AF8`; unique signature recorded in `research/native-world-conditional-loader.txt` |
| World variable comparison | RVA `0x343D8A`: Type1, Unknown10 variable, first Unknown8 operand |
| World location pair | RVA `0x343CF4`: Type32/33, Unknown14/Unknown18,47 means absent |
| World single location | RVA `0x343F52`: Type34/35/36/42, Unknown14 |
| World cost | RVA `0x343F16`: Type41, Unknown1C |
| World OP29 | RVA `0x343E50`: default branch writes Type then all Unknown8 operands; OP29/0 is Type29, Unknown8 `[0]` |

Battle field mappings are UnkType4 for the opcode, UnknownC plus Unknown14
for variable comparisons, CharaControlId plus Unknown14 for unit conditions,
and Unknown10 for event dispatch25/28. World variable1 uses Unknown10 plus
Unknown8; dispatch25/26 uses Unknown8; location32/33 and34/35/36 use the
verified location fields. World31 also takes the default array branch; the
adapter does not treat its unused Unknown10 column as a consumed variable.

The original Enhanced world cache now uses format
`world-r-t-v3-conditionals`, extracts EnhancedBattleEvent,
EnhancedWorldEvent and CharaControlId, and validates complete schema order.
`prepare_world_data` exposes `_RCCBattleConditions`, `_RCCWorldConditions`
and `_RCCCharaControls`. Tuple keys retain all three Nex keys.

## Applying source edits while preserving Enhanced content

RCC changes60 battle first-level groups and two world groups,1 and18.
Existing paired clauses keep their dispatch and receive only the authored
condition deletions or replacements. Source fallback clauses append after
the native existing clauses. Unchanged Enhanced opcodes, additional routes,
updated HP thresholds, metadata and character control aliases stay intact.
This also applies to first-level keys146+ for battle and44+ for world.

Enhanced converts some original world OP26 dispatches into a Type41 cost
guard plus Type25 event. An unchanged source terminal therefore preserves
that complete modern dispatch. World18's event301 changes its var159=1
guard to var110=53, while preserving the native Type25 event301 dispatch.
Five further source progression clauses for values54..58 append there;
world1 appends the source value42 clause. Added source OP26 clauses use the
verified native array encoding with all eight operands.

The ending has a specifically anchored adaptation. Native Battle144 replaces
the old variable128=0 guard with509=0 in event486/487 routes. The source
removes that guard, so the adapter removes its native509 equivalent there.
The same guard also gates two added Enhanced491 sibling routes; it is
removed consistently from those routes while retaining their Type33/34
character availability controls and dispatch. No global128-to509 alias is
introduced. Existing native CharaControlId1005/1006 and508 remain intact.
Inserted unit0 conditions use nonzero control alias256: ID0 means no record.

The verified native result changes162 existing battle clauses and adds27;
world changes one existing clause and adds six. Final Nex inventories are
2061 battle rows and552 world rows. The authored source-only fixture
reproduces every parsed source program exactly.

## Output guards and validation

`_RCCConditionalReplacements` contains complete expected/replacement rows
for two-key clause groups. The generic Nex builder recomputes the exact
source plan, checks every original expected row, replaces only declared
groups and rebuilds with FF16Tools. The converted result must match the
intended schemas, complete three-key inventory and every cell. Removing
rows is allowed only as part of this guarded source conditional plan;
ordinary sparse world/unit updates retain their existing-row restriction.

`tests/test_rcc_conditionals.py` has six targeted tests: raw source delta
equivalence, exact authored fixture behavior, feature scope, plan tamper
rejection, verified opcode/alias encoding, native modern-route preservation,
and real FF16Tools conversion of both conditional tables. All six passed on
the verified local inputs. This evidence is offline converter validation;
live Reloaded/game validation belongs to the final package run.
