# RCC port and remaining gameplay validation

Version0.6.0 implements RCC v27's r/i/s/a/y/j/m/u/z/f/t/p/w/c/o phases, active
patches.cfg defaults, built-in overworld/cleanup behavior and optional Fiesta/
Easy Mode codes for the verified Enhanced build. Ordinary and unique jobs share
s. Full redistribution remains available as a custom allocation mode.

See RCC-PARITY.md for the feature map and explicit Enhanced adaptations. The
generator keeps numeric IDs, input hashes, source/RNG comparisons and all native
patch RVAs/guards auditable. Original files and the installed loader DLL remain
unchanged. Classic and other Enhanced executable hashes are separate work.

## Delivery checks

Major changes use the AGENTS.md workflow: automated/source tests, actual
installed-serializer checks, backups, real Reloaded-II startup and fresh logs.
The guarded runtime has its own log. tools/verify_live.py compares every emitted
native patch/XML field and every merged Nex row/cell and binary/script asset.
Final evidence and the installed seed identity are under research/live-validation-0.6.0.
The managed bridge launch passed all 23 native ranges, 14 XML tables, 34 merged Nex
tables and 15 assets without errors/conflicts. AbilityData/SpawnData scans found
their original signatures. Only the existing Decode warning remains with its
alternate signature matched. All 37 original input hashes stayed unchanged.
No gameplay input has been performed during this validation.

A PS1-identical numeric seed is not claimed. Additional Enhanced rows and
reproducible phase-hashed Python3 RNG streams change exact outputs. Source
phase order, f's second reset, post-phase continuation and effective source
exceptions are maintained. Full's pools/counts intentionally follow the user's
additional settings.

Coverage concerns the implemented source phases, eight enabled patches.cfg
defaults, built-in changes and two secret codes. The commented optional XML
patch catalog is outside this port's current scope.

## Remaining gameplay work

1. Keep a backed-up post-intro test save with ordinary jobs unlocked, suitable
   learned skills, unique characters, monsters and required equipment/items.
   This avoids replaying cutscenes for each ability batch.
2. Test reactions by triggering their native conditions, equip supports/movement
   explicitly, and exercise each inventory/terrain/katana/parameter menu.
3. Play early story and random battles, recruit/rename units, buy/process poach
   rewards, run propositions, and check late bosses and ending progression.
4. Compare multiple seeds and chaos settings for campaign completion and balance.
   Record battle/seed/ability IDs rather than treating startup as gameplay proof.
5. Validate Classic independently if requested; retain the Enhanced hash guard.

These are gameplay-validation tasks, not missing randomization feature flags.
The Enhanced-only map127 encounter506/ENTD519 keeps original deployment
coordinates because no RCC terrain mesh exists for it. This documented terrain
exception and native field bounds remain visible in phase audits.
