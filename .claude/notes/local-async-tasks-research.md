# Local async tasks without Pub/Sub — research & recommendation

**Goal:** make background tasks run *asynchronously* in local dev (off the request
thread), without the Google Cloud Pub/Sub dependency, without running a second
process, and with behaviour "reasonably close to Pub/Sub". Bonus: a controllable
testing layer for injecting failures, slowness, and repeat delivery.

Date: 2026-07-12

---

## 1. How the task system works today

Django 6.0's native `django.tasks` framework, with a **pluggable backend** selected
by the `TASKS["default"]["BACKEND"]` setting.

| Environment | Backend | Behaviour |
|---|---|---|
| Prod (`settings_prod`) | `gyrinx.tasks.backend.PubSubBackend` | Fire-and-forget publish to a per-task Pub/Sub topic → push subscription POSTs to `/tasks/pubsub/` → handler runs the task in the same Cloud Run service |
| Dev + tests (`settings_dev`) | `django.tasks.backends.immediate.ImmediateBackend` | Runs the task **synchronously inside `enqueue()`**, on the calling thread |

Key components (all under `gyrinx/tasks/`):

- **`registry.py`** — explicit `TaskRoute` list (name → topic, ack deadline, retry
  delays, optional cron). A system check (`checks.py`) fails the build if a `@task`
  is not registered.
- **`route.py`** — `TaskRoute` dataclass: `ack_deadline` (10–600s), `min_retry_delay`,
  `max_retry_delay`, `schedule`. These are the Pub/Sub knobs.
- **`signals.py`** — lifecycle handlers listening on Django's `task_enqueued` /
  `task_started` / `task_finished` signals. They create/advance a **`TaskExecution`**
  row (a `Base` model with a `StateMachine`: READY → RUNNING → SUCCESSFUL/FAILED).
  **This is backend-agnostic** — it already works for both backends. Idempotent:
  `task_started`/`task_finished` skip if already in a later state (built for
  at-least-once redelivery).
- **`views.py::pubsub_push_handler`** — the prod executor. Decodes the envelope,
  looks up the route, sends `task_started`, calls `route._underlying_func(*args,
  **kwargs)`, sends `task_finished` (success or failure), returns 200 (ack) / 500
  (nack → redeliver) / 429 (DB at capacity → retry).
- **`provisioning.py`** — creates topics/subscriptions/Cloud Scheduler jobs on
  startup (prod only).

### The enqueue sites (7 real ones)

All fire-and-forget, most wrapped in `transaction.on_commit(...)`:

- `list.py` `refresh_list_facts` (dirty-list self-heal)
- `content/signal_handlers.py` `propagate_content_cost_change`, `refresh_list_facts`
- `core/models/list/signal_handlers.py` `propagate_default_child_fighter_assignment`
- `api/views.py` `trigger_discord_issue_action`
- `core/tasks.py` `backfill_pins`, `reconcile_all_lists` self-re-enqueue (maintenance chains)

The codebase is **already hardened for at-least-once delivery** — the task
docstrings are full of idempotency reasoning ("Pub/Sub is at-least-once, so a
redelivered batch can fork the chain…"). A local backend that can *reproduce*
redelivery is therefore genuinely valuable, not just cosmetic.

---

## 2. Constraints that shape the design

1. **The dev server is `manage runserver`** (threaded WSGI dev server, long-lived
   process, autoreloads on file change). Prod is `daphne` (ASGI) but prod keeps
   Pub/Sub — so daphne is out of scope here. Under runserver we *can* spawn
   background daemon threads.
2. **`settings_dev.py` is used for BOTH runserver and pytest.** So "async in dev,
   sync in tests" cannot be split by settings module alone — it needs a runtime
   discriminator. `settings_dev.py` already detects pytest via
   `os.getenv("PYTEST_CURRENT_TEST")` (line 20), so this is easy.
3. **~17 test call-sites depend on `.enqueue()` running synchronously** (plus 20
   `.func()` direct calls, which bypass the backend and are unaffected). A truly
   async test default would break them. Tests must keep eager/inline execution by
   default.
4. **pytest runs inside a transaction that is rolled back** (`@pytest.mark.django_db`).
   A background *thread* would open its own DB connection and *cannot see the test's
   uncommitted rows*, and `on_commit` callbacks don't fire unless captured. So a
   background-thread executor is fundamentally incompatible with the default test
   transaction model — reinforcing that tests want in-thread execution.
5. **No durability requirement in dev.** Losing queued tasks on a runserver reload is
   fine. (Pub/Sub is durable in prod; dev doesn't need to be.)

---

## 3. Options

### Option A — In-process thread-pool backend (RECOMMENDED)

A custom `InProcessBackend` with a small pool of **daemon worker threads** living in
the runserver process. `enqueue()` puts a message on an in-memory `queue.Queue` and
returns immediately (like Pub/Sub's fire-and-forget publish). Workers pull messages
and execute them through a **shared executor** (extracted from the push handler), so
the same signal/`TaskExecution` plumbing runs.

Pub/Sub fidelity we can reproduce:
- **at-least-once** → optional duplicate delivery; **retries** → re-queue on failure
  with exponential backoff bounded by `route.min_retry_delay`/`max_retry_delay`;
  **ack deadline** → soft execution-time budget from `route.ack_deadline`;
  **no DLQ** → after `max_attempts` mark FAILED (matches today's "it stops" behaviour).
- Worker closes its DB connection after each task (`close_old_connections`).

Three **modes** on one backend (chosen at runtime):
- `eager` (test default): run inline in `enqueue()` — behaviourally identical to
  today's `ImmediateBackend`, so all existing tests pass untouched.
- `threaded` (dev/runserver default): the real async worker pool.
- `manual` (opt-in in tests): enqueue into an inspectable buffer; the test drives
  delivery explicitly — this is the **testing layer**.

Worker pool is **lazy-started on first `enqueue()` in threaded mode**, so it never
spins up under `migrate`, `shell`, or pytest — no `AppConfig.ready()` process-type
guessing needed.

- **Pros:** no second process; genuinely async in dev; reuses `TaskExecution` +
  signals; the fault-injection knobs and `manual` mode directly satisfy the "testing
  layer" ask; small, self-contained.
- **Cons:** not durable across reloads (fine for dev); worker threads need disciplined
  DB-connection hygiene.

### Option B — Database-backed queue + in-process poller

Persist messages to a table (could extend `TaskExecution`), and a background thread
polls with `SELECT … FOR UPDATE SKIP LOCKED` + a visibility timeout. A dead worker's
row becomes visible again → redelivery. This is the *most faithful* Pub/Sub analogue
(durable, real visibility-timeout redelivery) and could even become a **future prod
backend that removes the GCP dependency entirely**.

- **Pros:** durable; survives reload; redelivery semantics are "real"; a credible
  path to dropping Pub/Sub in prod too.
- **Cons:** meaningfully more to build (poller, locking, claim/visibility, backoff
  columns); the polling worker still can't see a test's uncommitted transaction, so
  tests *still* need an eager/manual mode — i.e. you build Option A's test story
  anyway, plus a DB queue on top. Fault injection is clumsier through a real table
  than through an in-memory buffer you control.

### Option C — Adopt the `django-tasks` PyPI package's `DatabaseBackend`

The third-party `django-tasks` package (the reference impl that became
`django.tasks`) ships a `DatabaseBackend` + a `manage db_worker` command.

- **Rejected:** `db_worker` is a **second process** — violates the "no extra server"
  constraint. Django 6.0's *built-in* `django.tasks` only ships `immediate` and
  `dummy`; there is no built-in DB backend to reuse in-process.

### Option D — asyncio tasks on the event loop

Rejected: runserver is WSGI (no persistent event loop), and views are sync. Threads
are the right primitive here, not `asyncio`.

---

## 4. Decision & what was built

**Chosen: Option B (durable DB-backed queue), scoped local + test only** — prod keeps
Pub/Sub, untouched. The durable table buys the closest-to-Pub/Sub redelivery
semantics (visibility lease → reclaim on worker death) and the best test surface,
without any goal of replacing Pub/Sub in production.

Built (all under `gyrinx/tasks/`):

- **`executor.py`** — shared `run_task(...)` extracted from the push handler. Both the
  prod Pub/Sub handler and the local backend now run tasks through it, so dev/test and
  prod fire identical `task_started`/`task_finished` signals. `emit_signals=False` lets
  a *duplicate* delivery re-run the function without illegally resurrecting a terminal
  `TaskExecution`.
- **`models.py::QueuedTask`** — the durable queue row + `claim_one()` manager using
  `SELECT … FOR UPDATE SKIP LOCKED` and a visibility lease (`locked_until`).
- **`worker.py`** — `deliver()` (run one claimed row; delete on success, backoff-retry
  on failure, give up after `max_attempts`) shared by the pool and the test driver, plus
  `TaskWorkerPool` (daemon threads, lazy-started, DB-connection hygiene).
- **`local_backend.py::DatabaseBackend`** — modes `eager` (test/default, inline like
  ImmediateBackend), `worker` (dev-server async), `manual` (test-driven). Plus a
  process-wide mode override for the fixture.
- **`faults.py::FaultConfig`** — probabilistic chaos (duplicate/failure/drop/latency)
  for the dev server, from `OPTIONS["faults"]` or `TASKS_FAULT_*` env.
- **`testing.py`** — the `task_queue` pytest fixture + `ManualTaskQueue`
  (`deliver_all`/`deliver_next`/`fail_next`/`drop_next`/`redeliver_last`, `capture()`
  for on_commit enqueues).

Settings: base default → `DatabaseBackend` eager; `settings_dev` → `worker` when
`runserver` is in argv and not under pytest; `settings_prod` → `PubSubBackend`
(unchanged).

### State-machine gotcha handled

`TaskExecution` has sticky terminal states (SUCCESSFUL/FAILED) and raises on invalid
transitions — so naive redelivery of a completed/failed task would crash in the signal
handler (a latent gap the codebase's at-least-once assumptions never exercised locally).
Handled locally without touching prod semantics: a **retry** resets the row to READY
before re-running; a **duplicate** re-runs the function with `emit_signals=False`,
leaving the terminal record alone.

### Validation

- Full suite: **3187 passed, 13 skipped** (eager is a clean drop-in; the ~17
  sync-dependent enqueue tests still pass untouched).
- 13 new backend tests cover manual-mode redelivery, retry, real-exception recovery,
  give-up, drop, and a self-re-enqueue chain.
- Live checks against a real DB: worker mode runs a task on a background thread
  (`enqueue()` returns with status still READY); `TASKS_FAULT_DUPLICATE_RATE=1.0`
  produces a real duplicate delivery.

### Proposed shape

```
gyrinx/tasks/
  backend.py            # existing PubSubBackend (unchanged)
  local_backend.py      # NEW: InProcessBackend (eager|threaded|manual)
  executor.py           # NEW: execute_task(name, id, args, kwargs, enqueued_at)
                        #      — extracted from views.pubsub_push_handler,
                        #        reused by both the push handler and InProcessBackend
  faults.py             # NEW: FaultConfig (duplicate/failure/latency/drop/reorder,
                        #      seeded RNG) applied in threaded/manual modes
  testing.py            # NEW: pytest helpers/fixture — deliver_all(), deliver_next(),
                        #      redeliver_last(), fail_next(), assert_ran(...)
```

Settings wiring:
- `settings.py`: default `TASKS` → `InProcessBackend` with `mode="eager"`
  (drop-in for today's ImmediateBackend everywhere it isn't overridden).
- `settings_dev.py`: if **not** under pytest → `mode="threaded"` (+ fault knobs off
  by default, enable via env like `TASKS_FAULT_DUPLICATE_RATE`); if under pytest →
  keep `mode="eager"`.
- Prod unchanged (`PubSubBackend`).

Fidelity mapping to Pub/Sub knobs already on `TaskRoute`:
- `ack_deadline` → soft per-attempt execution budget (log if exceeded; optionally
  redeliver, mimicking a missed ack).
- `min_retry_delay`/`max_retry_delay` → exponential backoff between attempts.
- at-least-once → `FaultConfig.duplicate_rate`; lost publish → `drop_rate`
  (mirrors the real backend's documented fire-and-forget message-loss window).
- no dead-letter topic → stop after `max_attempts`, mark `TaskExecution` FAILED.

Testing layer (the fun part):
```python
def test_redelivery_is_idempotent(task_queue, ...):
    do_something_that_enqueues()
    task_queue.deliver_all()          # run once
    task_queue.redeliver_last()       # simulate at-least-once duplicate
    assert ...                        # one action, not two

def test_survives_transient_failure(task_queue, ...):
    do_something_that_enqueues()
    task_queue.fail_next()            # first attempt raises → backoff → retry
    task_queue.deliver_all()
    assert ...                        # eventually SUCCESSFUL
```

### Risks / things to get right
- **DB connections in worker threads** — `close_old_connections()` before and after
  each task; never share the request's connection.
- **runserver autoreload** — workers are daemon threads in the `RUN_MAIN` child; they
  die on reload. Acceptable; document it.
- **`manual` mode + `on_commit`** — enqueues happen in `on_commit`; tests using manual
  mode must wrap in `captureOnCommitCallbacks` (or use `transaction=True`). The fixture
  can encapsulate this.
- **Keep the shared executor honest** — extracting `execute_task` must not change prod
  behaviour; the push handler keeps its HTTP/OIDC/429 shell and only delegates the
  "run the task + fire signals" core.

---

## 5. Possible follow-ups (not built)

- A `manage run_tasks` command to drain the queue from a shell (handy for one-off local
  batch runs of the maintenance chains without the dev server).
- A tiny admin/status page showing queue depth + oldest available_at.
- Wire the probabilistic fault knobs into a documented `dev.sh --chaos` flag.
- Consider `max_attempts` / backoff surfaced on `TaskRoute` if per-task tuning is wanted
  locally (kept as a backend option for now to leave the prod-facing route clean).
