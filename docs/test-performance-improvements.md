# Measuring full-suite performance

The full suite already uses pytest-xdist and PostgreSQL. Compare changes
against a complete run of the same test selection on the same hardware,
with the same worker count. A faster focused suite or a warm reused database
does not establish a faster full suite.

## Recording a run

The measurement command provisions this worktree's Python and frontend
environment through `.codex/run.sh`, then runs pytest with the arguments given.
It records wall time, child-process CPU time, exit status, Git revision and
working-tree digest, and JUnit test counts under `logs/test-performance/`.
It returns pytest's exit status, including collection failures and empty
selections.

```bash
./scripts/measure_test_performance.sh --label baseline -- -n 4
# Apply the candidate change, then use the same arguments.
./scripts/measure_test_performance.sh --label candidate -- -n 4
```

Keep the PostgreSQL server configuration fixed, and avoid competing test runs
while comparing. Four workers are appropriate for a controlled comparison on
the shared development machine. A default local run uses pytest's `-n auto`;
benchmark that command separately before claiming a change to its elapsed time.

The worker count stays unchanged. The work-stealing scheduler can move pending
tests from a busy worker to an idle one when case durations differ, reducing
the wait for the last worker without adding processes or runners.

The normal full run recreates test databases from the current models, using
`--nomigrations`. Use identical database settings for each measurement.
`--reuse-db` is useful for development, but comparing a cold baseline to a warm
candidate measures database reuse as well as the code change.

Under pytest, the PostgreSQL schema editor creates unlogged tables only in
databases whose names start with `test_`. Constraints, indexes, transactions
and row locks still use PostgreSQL. Unlogged test data is disposable after a
database crash; development databases and ordinary migration commands keep
logged tables. The shared PostgreSQL server's durability settings are unchanged.
Only connections to these disposable test databases disable synchronous commit.
Set `GYRINX_TEST_UNLOGGED_TABLES=False` to compare ordinary logged test tables.

For a single-worker profile of an expensive test, after the full run finishes:

```bash
.codex/run.sh python -m cProfile -o logs/test-profile.pstats -m pytest \
  -n 0 --durations=20 path/to/test_file.py::test_name
```

## CI baseline

The exact starting commit, `42fdc46f3`, ran in
[38076349949](https://github.com/gyrinx-app/gyrinx/actions/runs/38076349949).
It completed all 13,826 tests with 13,811 passed, 13 skipped, one expected
failure and one existing campaign-gallery assertion failure in 1,864.56
seconds. The assertion expected the gang type and owner to have no intervening
markup, but the component now draws a gang-type icon there. The comparison
target is at most 932.28 seconds on the same four-worker runner.

Completed main run [38070805424](https://github.com/gyrinx-app/gyrinx/actions/runs/38070805424)
at `b74ccfeab` used four workers on the existing `ubuntu-latest` runner.
Its full-suite result was 13,802 passed, 13 skipped and one expected failure in
2,464.64 seconds. The full-suite step took 41 minutes 7 seconds and the job took
41 minutes 57 seconds. Halving that test execution time requires at most
1,232.32 seconds, without adding runners or increasing the runner size.

The local starting revision completed the same selection with four workers in
2,151.53 seconds, with the same existing gallery failure. Its comparison target
is at most 1,075.765 seconds. The gallery assertion has since been corrected on
main and that fix is retained here.

The first candidate, before the test consolidation pass, exceeded both targets.
Its local run was deliberately interrupted after 10,511 passing tests in
1,230.03 seconds, and its CI run was cancelled after exceeding the CI target.
These incomplete runs establish that the first candidate missed the target;
they are not full-suite passing results. The shared local cases used about 16%
less summed worker time, which is preliminary evidence only.

## Reducing repeated work

The consolidation pass keeps HTTP coverage at the boundaries where routing,
permissions, persistence, redirects or rendering are the contract. It moves
malformed-input permutations to database-free form tests and context-only
checks to the real context builders. Repeated assertions about the same page
or operation share one setup and response.

- Ingest and conversion scenarios share their unchanged input and successful
  application. Changed inputs, fault injection and rollback remain separate.
- Authoring registry and help guards inspect the registry directly. Populated
  listings still exercise every route, using one catalogue setup.
- Power advancements retain selected and random flows, access grades, stale
  choices, replay and history. Arbitrary family names no longer multiply every
  scenario; authored D6 endpoint flows pair with a six-position form test.
- Post-battle editor tests prepare real drafts through the shipped service.
  Entry, crew selection, permissions and application retain HTTP coverage.
- Maintenance delivery crosses the real batch boundary with eleven gangs
  instead of 115. Query growth, reset results and redelivery remain checked.
- Same-connection pause tests use rollback isolation. Actual outer commits,
  session locks and threaded concurrency retain transaction tests.

The pass also replaces vacuous checks: an empty filtered collection must be
nonempty before asserting every row is suppressed, and foundation status and
campaign actor checks target their actual data or rendered region.

Focused validation and complete local/CI comparisons are still in progress.
Neither the reduced test count nor isolated timings prove a 50% full-suite
improvement.
