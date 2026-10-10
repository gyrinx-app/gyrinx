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

The branch's initial local full-suite measurement and the candidate comparisons
are still being gathered. Query reductions in isolated profiles are preliminary
evidence; they do not prove a 50% full-suite improvement.
