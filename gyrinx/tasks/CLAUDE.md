# Tasks (background jobs)

Django 6.0 `django.tasks` with a Gyrinx-specific `TaskRoute` (retry + schedule
config) and **two backends that are never swapped**: production runs on Pub/Sub;
dev and tests run on an in-process durable queue. `DatabaseBackend` is never
selected in production, and `settings_prod.py` forces `PubSubBackend`.

Human-facing docs live in `docs/{explanation,technical-reference,how-to-guides}/task-framework.md`.
Design notes for the local backend: `.claude/notes/local-async-tasks-research.md`.

## Layout

- [`backend.py`](backend.py) — `PubSubBackend` (**production only**): fire-and-forget
  publish → Cloud Run push handler.
- [`local_backend.py`](local_backend.py) — `DatabaseBackend` (**dev + tests only**):
  in-process durable queue. Modes `eager` / `worker` / `manual` (see below).
- [`executor.py`](executor.py) — `run_task()`, the shared execution core. **Both**
  the prod push handler ([`views.py`](views.py)) and `DatabaseBackend` run the task
  function through it, so they fire identical `task_started` / `task_finished`
  signals and the same `TaskExecution` bookkeeping. Keep it that way — the two
  delivery paths must not diverge.
- [`worker.py`](worker.py) — `deliver()` (runs one claimed `QueuedTask` and settles
  it: delete on success, reschedule with backoff on failure, give up after
  `max_attempts`) and `TaskWorkerPool` (dev-server daemon threads). Dev/test only.
- [`faults.py`](faults.py) — probabilistic chaos (`TASKS_FAULT_*`) for the dev server.
- [`testing.py`](testing.py) — the `task_queue` pytest fixture + `ManualTaskQueue`
  driver (re-exported into `conftest.py`).
- [`models.py`](models.py) — `TaskExecution` (observability + state machine) and
  `QueuedTask` (the durable queue row).
- [`signals.py`](signals.py) — lifecycle handlers that maintain `TaskExecution`.
- [`registry.py`](registry.py) / [`route.py`](route.py) /
  [`discovery.py`](discovery.py) — task registration and per-task config. Apps
  declare their own routes in a `task_routes` list in their `<app>/tasks.py`;
  the registry collects them, so the platform names no edition task (#2093).
- [`provisioning.py`](provisioning.py) / [`apps.py`](apps.py) — Pub/Sub + Scheduler
  provisioning (Cloud Run only; skipped locally, in migrations, and in tests).

## Modes (DatabaseBackend)

- `eager` — base default in `settings.py`; the **test default**. Runs inline on
  enqueue, like `ImmediateBackend`. No `QueuedTask` row, so the suite stays sync.
- `worker` — the dev server. `settings_dev.py` switches to it when `runserver` is on
  the command line. Durable row + daemon-thread delivery with retries/backoff/leases.
- `manual` — tests, via the `task_queue` fixture. Durable row; the test drives
  delivery deterministically.

## Redelivery is at-least-once — mind the invariants

Delivery can happen more than once (Pub/Sub, or the worker pool after a lease
lapse). Two invariants live here:

1. **`TaskExecution` state** ([`signals.py`](signals.py)). `SUCCESSFUL` is the only
   sticky terminal state: a redelivery of a SUCCESSFUL task re-runs the function but
   leaves the record SUCCESSFUL. A redelivery of a FAILED task is a *retry* — the
   record is reset to READY *before* it starts, so the fresh attempt records its
   own outcome. So the two terminal states part company here: SUCCESSFUL must
   never go straight to RUNNING, while FAILED may — but only by way of that
   reset. **Never** let `handle_task_started` mark a terminal execution RUNNING
   directly; that is an illegal state transition that raises, and via the prod
   push handler becomes a 500 → Pub/Sub redelivery storm. Both handlers are `@transaction.atomic` and
   take a `select_for_update` lock on the execution row, because these guards are
   check-then-act: each step they take is a legal transition on its own, so the
   state machine's own row lock cannot catch two deliveries interleaving here.
2. **Business-logic idempotency is the task's job.** The propagation tasks take a
   `select_for_update` lock on the `List` row so two concurrent duplicate deliveries
   don't double-apply. Regression coverage:
   [`n23/core/tests/test_task_chaos_concurrency.py`](../../n23/core/tests/test_task_chaos_concurrency.py).

## Testing

- Default (eager): `enqueue()` runs the task synchronously — assert on its effect.
- Chaos: add the `task_queue` fixture (manual mode). Wrap the trigger in
  `task_queue.capture()` (fires `on_commit` enqueues), then `deliver_all()`,
  `redeliver_last()`, `fail_next()`, `drop_next()` to script adverse conditions.
- Do **not** start the worker pool in tests — its threads use their own DB
  connections and won't see the test transaction's uncommitted data. `manual` mode
  runs delivery in the test's own thread/transaction for exactly this reason.
