# Measuring full-suite performance

The full suite already uses pytest-xdist and PostgreSQL. Compare changes
against a complete run of the same test selection on the same hardware.
Keep the worker count fixed when isolating fixture changes; record it when
comparing different concurrency settings. A faster focused suite or a warm
reused database does not establish a faster full suite.

## Latest complete CI shard measurement

Head `90c7ead78` passed all 13,267 cases in
[CI run 38100163832](https://github.com/gyrinx-app/gyrinx/actions/runs/38100163832):
13,253 passed, 13 skipped and one expected failure. Both shard manifests record
clean merge revision `0093c14fe`, identical complete collections and exactly
one execution of every case. The coverage digest is
`d4dcf8a6d9782c4afcde2f483776e6f78741a708f74b885c34aae5f2c4b501d8`.
The earliest session start to latest finish was 773.71 seconds (12 minutes
54 seconds), 58.50% below the original 1,864.56-second baseline and below the
932.28-second target. Each existing four-CPU runner used four workers.

The required job took 861 seconds, including its companion wait; the companion
took 834 seconds and fresh-database 612 seconds. Their sum was 2,307 seconds
(38 minutes 27 seconds), 24.93% below the original 3,073 seconds. Both helpers
returned zero with clean source digests, measuring 503.12 and 776.75 seconds
and 3,130.32 seconds of combined child-process CPU. CI Checks also passed.

The local run selected the same cases but failed 16 Git/socket integration
checks because the filesystem sandbox blocked Git signing and localhost
listeners. It took 480.72 seconds, but is not passing performance evidence.
All 19 cases in the affected modules subsequently passed with approved host
access. A fresh full local run is required for the final candidate.

That measured revision used sharding only for exact-root PR changes. The
subsequent workflow applies it to all normal events, so the reduction persists
on main and narrower pull requests. This policy change still needs a complete
final-candidate measurement; the original targets remain unchanged.

## Previous complete unsharded measurement

Head `ffe0e513c` passes both full suites but still misses the 50% CI target.
Both runs selected 13,216 cases: 13,202 passed, 13 skipped and one expected
failure, with no failures or setup errors. Each recreated its test databases.

| Measurement | Original `42fdc46f3` | Head `ffe0e513c` | Reduction |
| --- | ---: | ---: | ---: |
| Full local suite | 2,151.53 seconds, four workers | 535.48 seconds, default twelve workers | 75.11% |
| Full CI suite | 1,864.56 seconds, four workers | 1,235.99 seconds, eight workers | 33.71% |
| Combined CI test-job time | 51 minutes 13 seconds | 32 minutes 15 seconds | 37.03% |

The clean local helper recorded 537.26 seconds of wall time and 1,590.21 seconds
of child-process CPU. [CI run 38097804821](https://github.com/gyrinx-app/gyrinx/actions/runs/38097804821)
measured clean merge revision `456fdfb28`: helper wall time 1,238.60 seconds and
child-process CPU 3,347.53 seconds. Its existing four-CPU runner tier exposed
an AMD EPYC 7763 in westus2. Required full-suite job time was 22 minutes
11 seconds, fresh-database 9 minutes 34 seconds, and the duplicate-omitting
job 30 seconds. CI Checks and migrations also passed. No runner size or
PostgreSQL server setting changed. Earlier successful timings below do not
replace this latest result.

The subsequent advancement-table query change and reconciliation with main's
founding fixture repair are not included in these complete measurements.
The query change fetches modifier scopes and effects through narrow prefetch
queries, retaining every fingerprint field and condition. Four paired HTTP
cases passed: call time fell from 17.31 to 16.31 seconds, total SQL time from
11.62 to 10.72 seconds, and profiled wall time from 26.39 to 25.70 seconds.
There were 132 more queries across the run; application CPU was approximately
unchanged (15.28 versus 15.39 seconds). These focused results do not establish
a full-suite reduction. All 187 advancement, power, progression and founding
activity cases passed, including stale requests, history, accounting and
query-growth guards. The existing condition-fingerprint case also checks
that an M2M-only profile membership change invalidates a saved roll after
restoring its independently tested scalar condition.

### Full-suite CI shard policy

On every normal CI event, `test` and `test-full` each collect the entire suite
and execute disjoint modules
using four workers on their existing runners. A module's SHA256 hash selects
its shard, so all cases in a module share one shard. The required full-suite
gate includes core and changed tests without executing a duplicate subset.
The core marker remains available for focused local checks.

Each shard uploads a collection and execution manifest, JUnit report and timing
record under a name containing the workflow run and attempt. The required
`test` job waits for `test-full` to succeed in that exact attempt, downloads its
artifact, and verifies the same merge revision, identical full collections,
deterministic disjoint selections, complete report phases and exactly one
completion per selected case. Failure, cancellation, missing evidence, worker
failure or mismatched collections fail the required check. Rerun all jobs
if an attempt omits the companion; earlier-attempt artifacts cannot satisfy it.

Compare the earliest pytest-session start to the latest finish across both
shards against the original 932.28-second CI target. Compare the sum of both
job durations, including the required job's wait, plus fresh-database against
the original 3,073 seconds. A passing shard alone proves neither the complete
suite nor the elapsed-time target. The exact-root implementation supplied
the complete CI result above; the all-events policy awaits final validation.

## Historical complete candidate

Candidate `c0f543979` passed both full-suite time targets on the same local
machine and unchanged CI runner size.
Each run recreated its test databases; neither used `--reuse-db`.

| Measurement | Original `42fdc46f3` | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Full local suite | 2,151.53 seconds, four workers | 645.74 seconds, default twelve workers | 69.99% |
| Full CI suite | 1,864.56 seconds, four workers | 798.73 seconds, eight workers | 57.16% |
| Combined CI test-job time | 51 minutes 13 seconds | 24 minutes 29 seconds | 52.20% |

The local run selected 13,272 cases: 13,258 passed, 13 skipped and one expected
failure, with no failures or setup errors. It used the same twelve-CPU macOS
machine as the original four-worker baseline. The original default twelve-worker
command failed during schema creation, so it supplies no usable timing baseline.
The candidate's dedicated schema-startup lock made that default command usable
without changing PostgreSQL settings. The helper recorded 647.78 seconds of
wall time and 1,661.76 seconds of child-process CPU time with a clean source digest.

[CI run 38092004429](https://github.com/gyrinx-app/gyrinx/actions/runs/38092004429)
measured clean merge revision `3f0f9ce09`: 13,282 passed, 13 skipped and one
expected failure among 13,296 selected cases. Its extra 24 cases came from main.
The same four-CPU runner tier used eight workers. The helper recorded 800.80 seconds
of wall time and 2,169.61 seconds of child-process CPU time, with no failures or
setup errors. Both pytest and helper elapsed times are below the 932.28-second
CI target; the local result is below its 1,075.765-second target.

The required full-suite job took 14 minutes 40 seconds, fresh-database took
9 minutes 18 seconds, and the job omitting duplicate execution took 31 seconds.
Their sum includes setup, PostgreSQL, frontend preparation and cleanup. No new
runners, larger machines or separate PostgreSQL server were added. CI Checks
and the fresh-database migration job also passed.

CI's PostgreSQL 16.4 had LLVM compilation available, with server `jit=on` and
`jit_above_cost=100000`. The real backend guard verified `jit=off` on disposable
test connections. Local PostgreSQL lacked LLVM support. The combined change
meets the targets; these measurements do not isolate each optimisation's share.

### Rerun after main changed

[CI run 38093156112](https://github.com/gyrinx-app/gyrinx/actions/runs/38093156112)
tested documentation head `31a950392` merged with newer main `8e9357d68`.
It selected 13,313 cases and finished with 13,298 passed, 13 skipped, one
expected failure and one failing founding-reopen assertion in 1,188.54 seconds.
The test's empty roster no longer met main's corrected reopening eligibility.
The compatibility fixture now hires an original member with a real founding
allowance before completing and reopening the action.

This rerun did not confirm the 50% CI target. Combined test-job time was
30 minutes 38 seconds, still below the original 51 minutes 13 seconds.
The helper measured 1,191.22 seconds of wall time and 3,212.49 seconds of
child-process CPU time. Matched, unchanged N23 cases also took about 48% longer;
the 17 added cases accounted for only about 43 summed worker-seconds.
Both runners exposed four CPUs and the same software image, but ran in
different regions. Their CPU model and frequency were not recorded, so runner
variability is a plausible explanation rather than an established cause.

Corrected head `55ca6ac55` passed all 13,313 selected cases locally and in
[CI run 38094767000](https://github.com/gyrinx-app/gyrinx/actions/runs/38094767000):
13,299 passed, 13 skipped and one expected failure. The local default
twelve-worker run took 547.16 seconds, 74.57% below the original baseline.
CI's unfiltered eight-worker run took 1,164.56 seconds, only 37.54% below its
baseline, so that revision still missed the 50% CI target. Combined CI
test-job time was 27 minutes 20 seconds, 46.63% below baseline. Its runner
exposed four CPUs on an AMD EPYC 9V74 in westcentralus; the original runner's
CPU model was not recorded. Further reductions need a full measurement before
the review handoff.

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
four worker processes on each of the two existing jobs as described above.
Earlier unsharded candidates used eight workers on one runner. The shard
policy adds no runners or larger machines.
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
was repeated without another observed pytest startup. That attempt also failed
during schema creation: 5,016 setup errors, twelve skipped cases and no tests
executed in 134.42 seconds before interruption. Neither attempt is a usable
baseline. The original twelve-worker command exceeds the available schema-lock
capacity. The valid original four-worker run is the local baseline, with the
candidate's default twelve-worker result recorded above and server settings
unchanged.

The subsequent merge from main retains the new hire-time Trade Points scenarios
and gallery examples. All 386 tests in the five affected gallery, founding,
asset-roll, fighter-action and post-battle modules passed in 82.58 seconds.

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

The first complete candidate met both time targets and the CI cost limit;
the latest rerun still misses the CI time target. Reduced test counts and
isolated timings remain supporting diagnostics rather than substitutes for
current full measurements.

### Further catalogue and lifecycle reductions

The ingest and progression pass combines assertions at the same lifecycle
stage, removing fifteen cases and nine duplicate initial imports. All 127
remaining cases passed in 69.68 seconds. A subsequent ordered run passed
twenty-seven promotion, empty-foundation and real seed cases, verifying that
the prepared promotion catalogue does not leak into later tests.

Choice, slot and rolling scenarios consolidate 250 cases into 168 while
preserving their domain assertions, permissions, accounting and query-growth
checks. Cosmetic CSS-class assertions are removed. The choice and rolling
catalogues are authored once per active module scope, with fresh ORM lookups
and player fixtures for every case. Function rollback restores any content
edits; module rollback removes the catalogue. These scopes contain ordinary
rollback tests, not threaded or transaction-flush scenarios.

Paired fresh-database four-worker runs passed: 250 original cases in 50.52
seconds, and 168 revised cases in 39.98 seconds. Child-process CPU time fell
from 75.98 to 51.73 seconds. Advancement runtime keeps all 39 test bodies,
including the real mid-draft reseed, while sharing its authored catalogue.
Its paired runs passed in 34.58 and 30.23 seconds; child CPU fell from 41.97
to 28.50 seconds. Eight ordered cases across these catalogues and a fresh
foundation also passed. These comparisons do not establish a full-suite
improvement; the next complete local and CI runs must measure that.

Ingest shares its real foundation within each ordinary class. The missing-seed
and full-clearing cases retain independent fixtures. Post-battle views share
their original three-characteristic catalogue; sandbox report classes share
only their XP and injury table. The independent roll-band catalogue stays
outside that shared scope. Paired four-worker runs passed all 284 unchanged
cases in 61.14 and 57.04 seconds, with child CPU falling from 100.46 to 89.40
seconds. All 48 status-choice cases also passed after registering the shared
fixture dependency used by their imported report fixture.

Founding budgets share the original seven-entry catalogue within ordinary
classes. Fighter-action repair cases share a clean standard graph, while
empty-ground, conflicting-content and dependency cases retain independent
setup. All 126 cases and their test bodies remain. Paired four-worker runs
passed in 38.53 and 34.59 seconds; child CPU fell from 55.90 to 46.83 seconds.
A single-worker ordered run passed twelve cases across repaired catalogues,
empty foundations, import mutations and clearing, independent roll-band
content, vehicle statlines and the advancement boundary.

The scheduler remains `worksteal`. An explicit catalogue-grouping trial passed
all 545 cases but supplied no evidence of a speed improvement, so its markers
were removed. These catalogue reductions still require complete local and CI
measurements on the resulting commit before the time target can be claimed.
