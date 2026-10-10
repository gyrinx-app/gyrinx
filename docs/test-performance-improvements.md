# Measuring full-suite performance

The full suite already uses pytest-xdist and PostgreSQL. Compare changes
against a complete run of the same test selection on the same hardware.
Keep the worker count fixed when isolating fixture changes; record it when
comparing different concurrency settings. A faster focused suite or a warm
reused database does not establish a faster full suite.

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

The work-stealing scheduler can move pending tests from a busy worker to an
idle one when case durations differ. Local runs retain `-n auto`. CI uses
eight worker processes on the existing runner size, allowing another worker
to run while one waits on PostgreSQL. It adds no runners or larger machines.
Verify the cost separately by comparing the sum of the required, full-suite
and fresh-database job durations, not just the fastest job.

When a PR changes the root conftest, the existing changed-test policy requires
the entire suite. CI measures an unfiltered full run in the required `test`
job for that exact `.` scope, and omits its duplicate execution in `test-full`.
Both jobs select against the same immutable PR base and verify the checked-out
revision. Selector errors fail the job. The second job's summary identifies
the required check as the owner of the full result; its own green status does
not prove that the suite passed. Other PR scopes, main and merge-group runs
retain their existing checks. Count the second job's remaining startup cost.

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
These connections also disable PostgreSQL's LLVM query compilation. Some
fixture reads have estimates above `jit_above_cost` despite returning only a
few rows; compilation can dominate short queries. This is a test-connection
setting, including thread connections. Ordinary databases retain their
settings. See [PostgreSQL's JIT guidance](https://www.postgresql.org/docs/16/jit-decision.html).
Set `GYRINX_TEST_UNLOGGED_TABLES=False` to compare the ordinary PostgreSQL
backend, including logged tables and its unchanged connection settings.

The pytest backend serializes schema creation on a dedicated, unpooled
maintenance connection to `postgres`. It holds the same advisory lock across
CREATE/DROP and Django's complete schema initialization, then releases the
connection on success or interruption. Tests execute in parallel after their
schemas are ready. This avoids simultaneous schema creation exhausting the
shared lock table without changing PostgreSQL settings. It requires access
to `postgres`; ordinary backends and logged-table comparison runs do not
participate, so unrelated startup can still exhaust the shared cluster.

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
target is at most 932.28 seconds on the same runner size. The three test jobs
used 51 minutes 13 seconds of runner time in total.

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

The first complete consolidation candidate, `4455741c6`, also missed the target:

| Measurement | Workers | Pytest elapsed | Result |
| --- | ---: | ---: | --- |
| Local | 4 | 1,440.05 seconds | 13,385 passed; two failures and one setup error |
| [CI 38082880416](https://github.com/gyrinx-app/gyrinx/actions/runs/38082880416) | 4 | 1,878.72 seconds | 13,348 passed; 40 failures |

The local failures were PostgreSQL shared-memory errors; all three cases passed
unchanged in a sequential rerun. The CI failures were missing equipment category
fixtures after a transaction test flushed the database. Its three test jobs
used 63 minutes 11 seconds in total, exceeding the starting cost. These results
do not establish the requested improvement. Subsequent candidates must fix
fixture isolation and pass complete local and CI measurements.

The next candidate, `e287fae0e`, passed the complete CI suite in
[38086394288](https://github.com/gyrinx-app/gyrinx/actions/runs/38086394288):
13,404 passed, 13 skipped and one expected failure in 1,316.64 seconds.
This is about 29% below the starting elapsed time, still above the target.
The run measured GitHub's clean merge revision `7fa32289f` on a four-CPU
runner, with eight workers. Its combined job cost exceeded the starting cost:
the required job took 40 minutes
4 seconds, the full job 22 minutes 46 seconds and fresh-database 6 minutes
54 seconds, totaling 69 minutes 44 seconds against the original 51 minutes
13 seconds. Both test jobs selected the whole suite on that candidate.

The subsequent clean local revision `6d81b09f6` passed the entire suite with
four workers: 13,336 passed, 13 skipped and one expected failure in 1,406.16
seconds. This is about 35% below the original 2,151.53 seconds, still above
the 1,075.765-second target. The helper recorded 1,408.34 seconds of wall time,
1,705.33 seconds of child-process CPU time and no failures or setup errors.
Further fixture and CI changes need new complete measurements.

The same branch head passed CI in
[38088790587](https://github.com/gyrinx-app/gyrinx/actions/runs/38088790587),
measuring GitHub's clean merge revision `f2fe8c357`. The full job selected
13,374 cases: 13,360 passed, 13 skipped and one expected failure in 2,165.29
seconds with eight workers on four CPUs. The helper recorded 2,168.57 seconds
of wall time and 3,910.23 seconds of child-process CPU time. This is slower
than the original CI baseline and does not demonstrate the target. The
required job also ran the full selection, taking 2,185.70 seconds in pytest.
Required, full and fresh-database jobs used 37 minutes 57 seconds,
36 minutes 53 seconds and 9 minutes 7 seconds respectively: 83 minutes
57 seconds in total. This reinforces the need to measure the next complete
candidate and remove the duplicated full execution.

An attempted default local baseline used the original revision's twelve workers.
It was stopped after 553 PostgreSQL shared-memory setup errors, with no tests
executed, while another worktree was also building test schemas. Its 78.79-second
partial result is not a performance baseline. The default-command comparison
still requires an isolated measurement window or a controlled database instance
with identical settings for both revisions.

## Reducing repeated work

The consolidation pass keeps HTTP coverage at the boundaries where routing,
permissions, persistence, redirects or rendering are the contract. It moves
malformed-input permutations to database-free form tests and context-only
checks to the real context builders. Repeated assertions about the same page
or operation share one setup and response.

- Ingest and conversion scenarios share their unchanged input and successful
  application. Changed inputs, fault injection and rollback remain separate.
  Ordinary ingest fixtures create the foundations their sheets read; clearing
  tests retain the complete catalogue and verify every foundation survives.
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
- Advancement skill selection and resolution reuse their local card and skill
  listings. Each new call reads fresh state; eligibility is captured before
  hypothetical stat previews mutate card nodes.
- Offers within one advancement read share the unfiltered catalogue and its
  default section. Each offer still gets independent placement, kind, owned
  and random-result filtering; the next public call reads fresh state.
- The advancement view derives its result and skill choices from one read
  before invoking any write. Operations resolve fresh state independently.
- Shared statline fixtures normalize the supplied values with the shipped
  formatter, then insert their cells in one statement. Stored blanks remain
  blank; production statline saves keep their existing behavior.
- Equipment category fixtures are restored after transaction-test flushes.
  Each test receives a fresh query, so scheduling an ordinary test after a
  transaction test cannot leave it with missing or stale categories.
- Gang legacy authoring and successful player flows share one graph and follow
  its lifecycle. All assertions remain, while 828 repeated authoring requests
  are removed. Forged selections, dismissal, withdrawal and query growth keep
  separate scenarios.
- Founding budgets share repeated seed and successful lifecycle scenarios.
  Buyer-to-stash and buyer-to-recipient movement remain separate, with fresh
  database state used for reconciliation. Permissions and query growth retain
  independent tests.
- Lasting effects seed-only checks build the shipped tables without unrelated
  characteristic modifiers. Sequential injury scenarios retain assertions at
  one, two, three and five injuries; collisions, history and cross-fighter
  isolation remain independent.
- Outcast rank matrices share their content while all five archetypes retain
  separate gangs and recruits. Leader, personal skill, Champion and removal
  assertions follow one lifecycle; all merged spending scenarios reconcile.
- Journal seed checks inspect the first complete seed before replaying it.
  Territory and House-table reads share unchanged graphs before real assignment
  and opening operations; staff visibility, rollback and maintenance delivery
  remain independent.
- Advancement action-flow tests share successful draft and correction
  lifecycles. Each skill tier retains its exact offered choices; dice modes,
  stale requests, ownership and later-rank refusal scenarios remain distinct.
- Crew tests create only the plain fighters each scenario needs, eliminating
  488 unrelated fighter creations while retaining every test and assertion.
  Whole-gang totals, random pools and query-growth data remain populated.
- Balance-sheet tests use the same priced fighter and real blank statline
  without twelve unused stat values. Purchases are checked and reconciled
  before removals; negative receipts are checked before price corrections.
- History reads share successful hire/refund, weapon and stat-change
  lifecycles. HTTP filters assert on the actual returned history events.
  Paging, snapshot windows, refusals and permission checks remain independent.
- Promotion cases share one real authored catalogue under a class transaction.
  Each case still creates fresh profiles, gangs, fighters and player records;
  per-test rollback restores the catalogue and class teardown removes it.
  Foundation conflict and preparation tests keep their separate setup.
  The class skips the first duplicate preparation in its fixture helper;
  the shipped attachment still prepares and repairs content for each case.
- Slot-choice tests share open, chosen and default/removal/rechoice lifecycles.
  All 219 assertions remain; refusal and query-growth cases are unchanged.
- Gang-archetype list permutations use the real hire-list builder. HTTP hire,
  player/staff visibility and query growth remain; compatible successful
  scenarios share their catalogue and prepared response.
- The equipment-category limit display uses ordinary rollback isolation.
  Its twelve assertions still check actual assignments at zero, one and
  three against a limit of two; it does not need a commit or full flush.
- Post-battle tests share compatible entry, refusal, application and receipt
  lifecycles. Status permutations inspect the real editor model, with one
  representative HTTP heading check. One-model cases omit an unused recruit;
  permissions, corrections, equipment and query growth remain distinct.
- Fighter-action tests replace cosmetic layout checks and fabricated action
  offers with structured panels and actual offered actions. Redirect-only
  route variants share unchanged drafts. Advancement boundary tests use
  isolated stat results so an unrelated characteristic cannot rescue a pass.
- Canonical seeders fetch existing definitions once per restoration and retain
  normal model saves, signals and history inside three atomic callbacks.
  Their references are local to the invocation. This assumes serial fixture
  initialization/flush on each worker's dedicated test database; unexpected
  competing inserts fail instead of receiving an upsert retry.

The advancement skill-choice page was inspected with `manage inspect_page` and
the Debug Toolbar, using a local agent's gang with an earned advancement, owned
choices and populated primary skill and power choices. Growing the offered list
from two to fourteen choices kept all three measured GETs at 302 queries, with
78 similar groups and 88 duplicate groups. Sharing catalogue loads within each
advancement read reduced all three GETs of the fourteen-choice page to 224
queries, with 77 similar groups and 87 duplicate groups. Reusing that read for
the view's skill choices reduced all three GETs further to 126 queries, with
19 similar groups and 12 duplicate groups. Existing result-count and power-count
growth tests also passed. These query counts describe that page's work; they do
not establish a full-suite time improvement.

The pass also replaces vacuous checks: an empty filtered collection must be
nonempty before asserting every row is suppressed, and foundation status and
campaign actor checks target their actual data or rendered region.

All 575 cases in the latest eight-module fixture/lifecycle validation passed
in 264.99 seconds. A separate ordered, single-worker run passed all 26
promotion cases followed by seven preparation/conflict/migration cases:
33 passed in 177.14 seconds. The preparation test explicitly starts without
the Advancement action, confirming the class catalogue was rolled back.
These focused results precede the subsequent fixture refinements. The next
369-case run passed 367 cases and found two incorrect revised assertions:
Movement includes its inch suffix, and tier links include a return URL.
Both corrected cases passed in a focused rerun. This run includes the latest
promotion fixture, post-battle and fighter-action reductions and backend guards.

A single-worker run also passed all 16 weapon and pause cases in 38.96 seconds.
An independent verification plugin checked the exact canonical catalogue and
history counts after five real transaction-test flushes. It also verified that
the seeders correct canonical fields while preserving existing extra-stat,
statline-link and equipment-category overrides and their history behaviour.

Focused validation and complete local/CI comparisons are still in progress.
Neither the reduced test count nor isolated timings prove a 50% full-suite
improvement.
