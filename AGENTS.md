# Validation for major changes

The user now requests automated tests and real Reloaded-II validation for
major changes rather than every iteration. Major changes include a new
allocation mode, changes to native table layouts or execution mechanics, and
monster randomization in random battles. Routine text/configuration edits and
small corrections need only the targeted checks justified by their impact.
For a major change, serializer-only and offline checks do not replace a real
Reloaded-II launch and fresh-log review.

Run the automated tests and `tests/validate_loader_xml.ps1` with the installed
FFTIC loader first. Back up any installed files changed for the test, preserve
the active seed and unrelated values when implementing requested rule changes,
record the new settings, and launch Enhanced through its existing Reloaded-II
application configuration. Inspect a fresh log for successful application of
every emitted table and for deserialization errors, failures, or conflicts.
Document existing loader warnings separately; do not call a log warning-free
when it is not. Close only the game session started for validation.

Keep executable hashes, layouts, discovered paths/RVAs, and live validation
evidence in `docs/RESEARCH.md` and `research/live-validation/` or its versioned
siblings. Keep the complete ability catalog and allocation coverage auditable;
do not silently reduce the full pool to caster spells. A successful
startup is not a completed-battle or campaign-balance test. If live validation
cannot run, report that limitation before delivering an unvalidated change.
