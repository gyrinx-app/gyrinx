# Counter migration volume evidence

Rehearsed on 2026-09-15 at records commit `d9893a2f3`, including the final
generated migrations through `n26.0071`. The database was a new, explicitly
guarded PostgreSQL scratch database populated only with synthetic rows. It was
not cloned from a player database. Production supplied aggregate volumes via
earlier read-only queries; this rehearsal made no production connection or
write.

## Fixture

- 19,940 counter values across 20 gangs
- 863 zero and 19,077 nonzero values
- 17,268 active and 2,672 archived counter assignments
- 228,571 pre-existing ledger events, including 2,643 `removed` events with
  assignment references

The script records every counter-value ID, assignment FK and value; every
assignment ID, gang-root FK and archived flag; every removal reference; and a
SHA-256 digest over every concrete field of every pre-existing ledger event.

## Results

- A forced exception after the real 0069 checkpoint function proved **0069's
  own atomic transaction** rolled back in 9.451 seconds. Migration 0069 was not
  recorded as applied, no checkpoint remained, and all old rows and the full
  journal digest were exact.
- The real forward path through 0071 took 12.241 seconds and created exactly
  19,940 migration-owned checkpoints. Every checkpoint used the deterministic
  migration batch, the exact assignment and gang, and
  `before == after == CounterValue.value`, with `delta == 0`.
- All 228,571 pre-existing journal rows remained byte-for-byte equivalent at
  the field-value digest level. All 2,643 removal references and all counter,
  assignment, gang, archived and value fields were unchanged.
- Reverse to the pre-0069 leaf took 19.295 seconds. It removed only checkpoints
  owned by 0069's deterministic batch; a later checkpoint with another batch
  survived. A counter opened and tallied after migration retained its pinned
  value through reverse.
- Reapply through 0071 took 12.352 seconds. It recreated one checkpoint for
  every then-current counter, retained the unrelated checkpoint, and again
  preserved the complete old-journal digest and pinned values.
- Total runtime, including fresh schema setup and fixture creation, was 330.958
  seconds. The pre-existing ledger digest was
  `51b17f870442eb7203392ff680efb55e3290081332b02fa8cc8cde127714c2fe`.

The rollback result applies to migration 0069's atomic transaction. It does not
claim that the separate 0069, 0070 and 0071 migrations form one transaction.

## Rolling-deployment limit

The rehearsal deliberately persisted both legacy writer shapes after the
checkpoint:

- Updating an existing counter and writing the old fixed-format `tallied` note
  left reconciliation reporting `value pinned 17, events end at 13`.
- Creating a new counter and writing only the old `tallied` note left
  reconciliation reporting `no counter opening event`.

These are expected gaps in the current design. Migration 0069 cannot checkpoint
writes made afterward by an old application worker, and old code does not fill
the structured counter columns. This was a persisted-shape experiment, not a
true concurrent traffic test.

Deploying this design therefore requires an externally enforced pause of
counter writes and a drain of old in-flight application work before migrations
start. Counter writes must remain paused until the new revision is serving and
old workers cannot resume. The repository does not itself establish that
maintenance switch or drain. This is a deployment prerequisite, not approval
to deploy.

## Reproduce

Run `.claude/notes/counter-migration-volume-evidence.py` only against a newly
created PostgreSQL database whose name begins
`wren_counter_migration_evidence_`. The script refuses a non-empty database or
a name outside that prefix. The successful run used
`wren_counter_migration_evidence_final4_20260915`, which was dropped after the
evidence was recorded.
