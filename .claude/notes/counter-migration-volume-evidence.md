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
to both `n26` 0068 leaves, created exactly the production counter-value volume,
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
