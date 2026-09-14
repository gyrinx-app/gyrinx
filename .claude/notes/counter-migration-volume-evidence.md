# Counter checkpoint migration volume evidence

Validated `n26/core/migrations/0069_fighter_action_records_and_counter_events.py`
on 2026-09-14 against a disposable PostgreSQL database cloned from the
worktree database. Production was queried read-only for aggregate counts only.

## Production shape

- Counter values: 19,940
- Zero values: 863
- Nonzero values: 19,077
- Counter assignments archived: 2,672
- Counter assignments active: 17,268
- Counter assignments with a historical `removed` event: 2,643
- Existing ledger events: 228,571

## Rehearsal

The script `counter-migration-volume-evidence.py` migrated a scratch database
to the final `n26` 0068 state (which includes the Activity rename), created exactly the production counter-value volume,
then applied the real 0069 migration with `MigrationExecutor`. Synthetic rows
matched the production zero/nonzero and active/archived distributions, with
2,643 removed-event references among archived assignments.

The first real migration attempt exposed a PostgreSQL failure:

`cannot CREATE INDEX "n26_ledgerevent" because it has pending trigger events`

The checkpoint insert creates foreign-key trigger events in the migration-wide
transaction. Django executes deferred schema-editor index statements before
that transaction commits. Calling `connection.check_constraints()` after the
forward insert flushes those triggers while preserving one atomic migration.
The reverse checkpoint deletion needed the same flush before later constraint
DDL. Both paths were fixed in 0069 and the full rehearsal was repeated from a
fresh clone.

## Result

- Forward migration: 11.735 seconds
- Reverse migration: 19.865 seconds
- Checkpoint events created: 19,940, exactly one per counter value
- Every `CounterValue` ID, assignment FK, and value was unchanged
- Every assignment ID, gang-root FK, and archived flag was unchanged
- Every pre-existing `removed` event reference was unchanged
- Every checkpoint had the assignment's exact gang link
- Every checkpoint had `before == after == CounterValue.value` and `delta == 0`
- Zero, nonzero, active, archived, and removed rows were all covered
- Reverse removed every checkpoint and preserved all counter values,
  assignments, and prior removed events

No semantic discrepancy remained after the constraint-trigger flush. The
scratch database contained no production records and production received no
writes.

The final dependency graph and 500-row insert batches were rehearsed again.
The PostgreSQL implementation of `check_constraints()` in Django 6.0.7
executes `SET CONSTRAINTS ALL IMMEDIATE` followed by `SET CONSTRAINTS ALL
DEFERRED`; it is not the base backend's empty method. The final run preserved
all values and references and passed the complete forward/reverse comparison.

Final batched run:

```json
{
  "active_assignments": 17268,
  "archived_assignments": 2672,
  "checkpoint_before_after_delta_and_gang_exact": true,
  "checkpoint_events": 19940,
  "counter_values": 19940,
  "database": "wren_counter_migration_evidence_batched",
  "elapsed_seconds": 11.598,
  "nonzero_values": 19077,
  "preserved_assignment_rows": true,
  "preserved_counter_value_rows": true,
  "preserved_removed_events": true,
  "removed_assignments": 2643,
  "reverse_elapsed_seconds": 18.38,
  "reverse_removed_only_checkpoints": true,
  "zero_values": 863
}
```
