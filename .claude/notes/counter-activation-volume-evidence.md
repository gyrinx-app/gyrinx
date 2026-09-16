# Counter activation rehearsal

Rehearsed on 16 September 2026 at activation commit `82c70453f` using a new,
empty local PostgreSQL database. All data was synthetic. Its size matches the
aggregate counts observed on 15 September; this run did not connect to production.

## Data and comparisons

The fixture contains 19,940 counters across 20 gangs, including 863 zero balances
and 2,672 archived assignments. It also contains 228,571 existing journal events,
including 2,643 removal references.

At each stage the script compares every counter ID, assignment reference and
balance, every assignment's gang and archived flag, and every removal reference.
It compares a SHA-256 digest of all fields of all pre-existing journal events.

## Results

1. Schema migration completed with tracking inactive and no counter checkpoints.
   All existing values and journal data were unchanged.
2. Both an old writer's persisted shape and the new inactive writer updated a
   counter before activation. Neither needed a checkpoint at deployment time.
3. An injected gang failure left 18,943 checkpoints, tracking inactive and writes
   paused. Earlier successful gangs retained their checkpoints.
4. Recorded cleanup removed that failed run's checkpoints. It preserved all
   balances and existing events. Writes resumed only through the operator action.
5. An ordinary counter edit then changed the sample balance from 44 to 47.
   The later activation recorded the new balance, not the abandoned checkpoint.
6. Successful activation created exactly one checkpoint per counter, including
   archived counters, and checked the complete structured counter histories before
   setting tracking active. It still left writes paused.
7. Duplicate task delivery preserved the exact checkpoint IDs and count.
8. After manual resume, a payment recorded `before=47`, `delta=-4`, `after=43`.

The journal digest immediately before successful activation covered 228,574
events, including the three intervening counter edits:

```text
cf8c8e0bc333cbe724c3a6ae83e25821ff64d253d29de59bc470044b601e6fe8
```

| Stage | Local seconds |
| --- | ---: |
| Schema migration after creating the legacy fixture | 24.479 |
| Activation with an injected failure | 4.617 |
| Cleanup of the failed run | 3.372 |
| Successful activation, including validation | 7.486 |
| Entire rehearsal, including initial schema and fixture setup | 318.800 |

These measurements describe synthetic local data spread over 20 gangs. They do
not predict production duration, real gang-size distribution or waiting for live
requests to drain. Separate two-connection tests exercise writer draining. The
old/new writer check here reproduces their persisted shapes sequentially.

## Reproduce

The script refuses databases outside `wren_counter_activation_evidence_` and
refuses any non-empty database. Use a fresh owned name each time:

```console
.codex/run.sh createdb wren_counter_activation_evidence_example
.codex/run.sh env DB_NAME=wren_counter_activation_evidence_example python .claude/notes/counter-activation-volume-evidence.py > .claude/notes/counter-activation-volume-evidence-result.log 2>&1
.codex/run.sh dropdb wren_counter_activation_evidence_example
```

The activation job uses the normal durable local task queue and delivery path.
Its expected injected failure is recorded as a failed maintenance run; handling
that failure is itself a successful task delivery, so it is not retried by the
queue. The operator chooses retry or cleanup. Focused tests separately exercise
retrying the same failed run and preservation of unrelated checkpoints.
