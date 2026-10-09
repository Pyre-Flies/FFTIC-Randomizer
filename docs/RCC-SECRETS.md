# Optional RCC secret modes

`fftic/rcc_secrets.py` ports the optional `fiesta` and `easymodo` code paths
from RCC v27 (`ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070`). These are separate
boolean settings for the parent CLI/GUI/package integration; they are not
additional letters in the ordinary feature string.

The verified source order is:

1. Unit palette cleanup, proposition cleanup, recruit normalization and
   Orbonne ally control (`randomizer.py:5239-5260`).
2. `setup_fiesta` if enabled (`5267-5268`).
3. Easy mode if enabled (`5270-5275`).
4. Final data writes. No extra unit cleanup occurs after the secret modes.

Neither secret consumes random numbers. The source order matters when both
are enabled: easy mode can overwrite a generic enemy's newly assigned fiesta
job. Existing nonenemy party palettes are preserved after fiesta changes
their jobs; another palette-cleanup pass would change the source outcome.

## Fiesta

The source newgame Ramza job constants become Mime93.
`fftic/rcc_fiesta_native.py` supplies the verified native equivalent through
the common exact-build runtime patch plan; original PS1 addresses are never
applied to the Enhanced executable.

The canonical starting-party ENTD is392 (`0x188`). All sixteen template
records get SecondarySkillset0 and Reaction/Support/Movement511. Party slots
0,2,3,4,5 become Mime93, unlock Mime at level1, and receive automatic
left-hand/head/body/accessory equipment254. Their specifications are:

| Slot | Sprite/gender | Bravery | Faith |
|---|---|---|---|
| 0 | Ramza1, male | 69 | 69 |
| 2 | Generic128, male | 70 | 40 |
| 3 | Generic129, female | 70 | 40 |
| 4 | Generic128, male | 70 | 70 |
| 5 | Generic129, female | 70 | 70 |

Nonparty slots through7 unlock job0 at level1, use Stone Gun73, and receive
left-hand/head/body/accessory255. Enemy units in ENTD387/388 receive Stone
Gun73. Other fields retain the final preceding phase values.

Two source quirks are explicitly preserved:

- The `u.righthand=0x49` statement inside the party-member loop writes the
  previous sixteen-unit loop's last variable, ENTD392/slot15. It does not
  give every party member a Stone Gun. Party right hands retain their prior
  values.
- `setup_fiesta` writes ten Mime-requirement bytes directly to the source
  image. Later, the final cached `JobReqObject.write_data` recomputes and
  rewrites that entire row from its job requirement attributes. The direct
  patch is therefore overwritten. The port preserves the final requirement
  tree produced by the preceding requirement phase instead of making this
  ineffective intermediate patch survive.

The latter behavior is verified using the literal original final writer,
not inferred from a comment or intended feature description.

## Easy mode

Every enemy-flagged unit becomes level1. If its sprite is128,129 or130, its
MainJob becomes28, Delita's sister's job. Special sprites retain their job.
The source sprite predicate includes ordinary monsters; the port does not
silently substitute a human-only rule. Ally records retain their levels/jobs.

## Interface and evidence

```python
apply_secrets(before, result, seed='', *, fiesta=False, easymodo=False,
              engine=None, fiesta_native=None)
```

The caller runs it after `finalize_cleanup` and before final metadata
reconciliation/emission. The reused UnitEngine operates on shared canonical
`_RCCUnitContext` rows. By default, `fiesta_native(before, result)` is the
bundled `rcc_fiesta_native.apply_fiesta_native` helper. It adds the verified
native newgame-job plan and returns a JSON audit; an unavailable helper or
changed original bytes fails explicitly. Native plans are
serialized/deployed by the parent runtime package, not by this module.

`_RCCSecretAudit` includes enabled switches, actual phase order, changed
unit owners/fields, source quirks and the native helper's receipt. Disabled
settings only emit an empty audit. There is no code-entry UI or hidden string
parsing in this standalone module.

All five tests in `tests/test_rcc_secrets.py` passed against literal source:
fiesta field equality and file-write requests, easy-mode enemy/sprite rules,
combined ordering, no extra RNG/cleanup, the overwritten Mime requirement
row, disabled settings and failure before unit mutation when a native guard
rejects. Four focused native tests also verify the instruction encoding,
independent caller/layout guards, unaffected spawn branches and canonical
secret integration. Live game validation is owned by the parent.

## Verified native Fiesta initialization

The original source changes two initial-job assignments at PS1 file offsets
`0x56894` and `0x568B0`. Enhanced represents this job once in its compact
actor record; conversion propagates that field into the decoded actor and
the expanded current-job field. The verified path is:

| Role | Enhanced RVA/evidence |
|---|---|
| Modern newgame selects mode0 | `0x37E033`: `xor ecx,ecx`; call `0x37FF14` |
| Mode dispatcher | `0x37FF52` calls reset `0x284500` |
| Newgame roster reset | `0x284500`; clears54 compact actors; mode0 calls allocator with type2 at `0x284534` |
| Compact actor allocator | `0x27528C`; calls initializer `0x275310` at `0x2752CB` |
| Ramza branch | `0x27538A` sets type2; `0x27538F` preserves graphic1 |
| Initial current job | `0x275392`: `mov byte ptr [rcx+2],r13b`, where the guarded prologue sets r13=1 |
| Compact to decoded actor | `0x27679C` reads compact+2; `0x27679F` writes decoded actor+3 |
| Expanded current job | `0x284AEC` reads compact+2; `0x284AF1` writes expanded current-job word+0x24 |

The four-byte job store changes from `44 88 69 02` to `C6 41 02 5D`, a
same-length `mov byte ptr [rcx+2],93`. Both instructions preserve CPU flags.
The preceding graphic store, male flags, stat/equipment profiles, name
identity and unrelated uses of r13=1 remain unchanged. Generic male/female
and monster branches remain byte-for-byte identical.

All direct initializer callers were traced. The allocator's other caller
passes type3 for monster breeding; the Soldier Office generator passes only
type0/1. No absolute function-pointer references to the initializer or
allocator exist in this verified image. The Ramza/type2 branch is therefore
the same native newgame initialization intended by the source patch.

The helper checks the exact executable SHA256, the original target
instruction and five independent byte-range hashes covering type dispatch,
allocator, newgame reset, job propagation and modern newgame mode selection.
It appends one four-byte `_RCCNativeTablePatches` plan and does not edit the
game executable or installed loader. Repeated planning is rejected.

Evidence is reproducible through the read-only `research/fiesta_re.py`
caller/RIP-reference scanner and `research/qol_re.py` disassembler. Saved
results include `fiesta-spawn-initializer.txt`, `fiesta-spawn-callers.txt`,
`fiesta-spawn-allocator-callers.txt`, `fiesta-newgame-callers.txt`,
`fiesta-modern-newgame.txt`, `fiesta-actor-fields.txt` and
`fiesta-expanded-actor-copy.txt` under `research/`.
