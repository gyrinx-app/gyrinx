# Task Framework How-To Guides

Practical recipes for common task operations.

## Create a New Task

### Prerequisites

- Python function that can be serialised (JSON-compatible arguments)
- Understanding of what work the task will do

### Steps

1. **Define the task function** in `gyrinx/core/tasks.py`:

```python
from django.tasks import task

@task
def send_notification(user_id: str, message: str):
    """Send a notification to a user."""
    from n23.core.models import User

    user = User.objects.get(pk=user_id)
    # ... send notification logic
```

1. **Register the task** in `gyrinx/tasks/registry.py`:

```python
from n23.core.tasks import send_notification

def _get_tasks() -> list[TaskRoute]:
    global _tasks
    if _tasks is None:
        from n23.core.tasks import (
            # ... existing imports
            send_notification,
        )

        _tasks = [
            # ... existing tasks
            TaskRoute(send_notification),
        ]
    return _tasks
```

1. **Enqueue the task** from your application code:

```python
from n23.core.tasks import send_notification

# Enqueue for async execution
send_notification.enqueue(user_id=str(user.pk), message="Welcome!")
```

### Notes

- All arguments must be JSON-serialisable (strings, numbers, lists, dicts)
- Use string UUIDs rather than UUID objects
- Import the task lazily in `_get_tasks()` to avoid circular imports

## Schedule a Task to Run Periodically

### Prerequisites

- An existing registered task
- Understanding of cron syntax

### Steps

1. **Add a schedule** to the task registration:

```python
TaskRoute(
    cleanup_expired_sessions,
    schedule="0 3 * * *",  # Daily at 3am UTC
)
```

1. **Optionally specify a timezone**:

```python
TaskRoute(
    send_daily_digest,
    schedule="0 9 * * *",      # Daily at 9am
    schedule_timezone="Europe/London",
)
```

1. **Deploy** - The Cloud Scheduler job is created automatically on startup.

### Common Schedules

| Schedule | Expression |
|----------|------------|
| Every 5 minutes | `*/5 * * * *` |
| Every hour | `0 * * * *` |
| Daily at midnight | `0 0 * * *` |
| Weekly on Monday | `0 0 * * 1` |
| Monthly on the 1st | `0 0 1 * *` |

## Add a Kill Switch to a Task

Kill switches let you disable tasks at runtime without redeploying.

### Steps

1. **Add a setting** in `settings.py` that reads from an environment variable:

```python
# settings.py
ENABLE_BATCH_JOB = env.bool("ENABLE_BATCH_JOB", default=True)
```

1. **Check the setting** at the start of your task:

```python
from django.conf import settings
from django.tasks import task

@task
def expensive_batch_job():
    if not settings.ENABLE_BATCH_JOB:
        logger.info("Batch job disabled via ENABLE_BATCH_JOB")
        return

    # ... rest of task
```

1. **Document the setting** in `docs/deployment-environment-variables.md`.

1. **Disable in production** by setting the environment variable:

```bash
# In Cloud Run environment variables
ENABLE_BATCH_JOB=false
```

## Configure Retry Behaviour

Adjust how Pub/Sub retries failed tasks.

### Steps

1. **Set retry parameters** in the task registration:

```python
TaskRoute(
    process_large_file,
    ack_deadline=600,      # 10 minutes to complete before retry
    min_retry_delay=60,    # Wait at least 1 minute before retry
    max_retry_delay=1800,  # Cap backoff at 30 minutes
)
```

### Guidelines

| Scenario | `ack_deadline` | `min_retry_delay` | `max_retry_delay` |
|----------|----------------|-------------------|-------------------|
| Quick task (<10s) | 60 | 10 | 300 |
| Normal task (<1m) | 300 | 10 | 600 |
| Long-running task | 600 | 60 | 1800 |
| Database-intensive | 300 | 30 | 600 |

### Notes

- `ack_deadline` is the time before Pub/Sub assumes the task failed
- Retry delay uses exponential backoff between min and max
- For database-intensive tasks, longer delays help avoid overwhelming the database

## Make a Task Idempotent

Tasks may be delivered more than once. Design for idempotency.

### Pattern 1: Check Before Acting

```python
@task
def backfill_user_data(user_id: str):
    from django.db import transaction

    with transaction.atomic():
        # Lock the row to prevent races
        user = User.objects.select_for_update().get(pk=user_id)

        # Check if already processed
        if user.data_backfilled:
            logger.info(f"User {user_id} already backfilled, skipping")
            return

        # Do the work
        user.backfill_data()
        user.data_backfilled = True
        user.save()
```

### Pattern 2: Upsert Operations

```python
@task
def sync_external_data(external_id: str):
    data = fetch_from_external_api(external_id)

    # update_or_create is naturally idempotent
    ExternalRecord.objects.update_or_create(
        external_id=external_id,
        defaults={"data": data, "synced_at": timezone.now()},
    )
```

### Pattern 3: Idempotency Keys

```python
@task
def send_email(email_id: str):
    # Use the email_id as an idempotency key
    if SentEmail.objects.filter(email_id=email_id).exists():
        logger.info(f"Email {email_id} already sent")
        return

    # Send and record
    send_email_to_user(...)
    SentEmail.objects.create(email_id=email_id)
```

## Test a Task Locally

There is no Pub/Sub locally — the [`DatabaseBackend`](../../gyrinx/tasks/local_backend.py) stands in. How it runs depends on the mode.

### In tests, tasks run inline (eager mode)

Under pytest the backend is `DatabaseBackend` in `eager` mode, so `enqueue()` runs the task synchronously — no Pub/Sub, no threads, no emulator:

```python
from n23.core.tasks import refresh_list_facts

# Runs synchronously and returns once the task has executed.
refresh_list_facts.enqueue("list-uuid-here")
```

To bypass the framework entirely and call the underlying function directly:

```python
refresh_list_facts.func("list-uuid-here")
```

### On the dev server, tasks run asynchronously (worker mode)

`scripts/dev.sh` runs `runserver`, which selects `worker` mode: enqueued work leaves the request thread and runs on an in-process daemon-thread pool, close to how production behaves. Watch the runserver log to see delivery. To exercise adverse conditions, see [Run the dev server with async tasks and fault injection](#run-the-dev-server-with-async-tasks-and-fault-injection).

## Test Redelivery, Failure, and Message Loss (the `task_queue` fixture)

Production delivery is at-least-once: a task can be delivered twice, fail and retry, or (rarely) be lost. The `task_queue` fixture puts the backend in `manual` mode so a test can script these conditions deterministically and assert the task is idempotent.

The fixture yields a `ManualTaskQueue` ([`gyrinx/tasks/testing.py`](../../gyrinx/tasks/testing.py)):

| Method | Purpose |
|--------|---------|
| `capture(execute=True)` | Context manager that fires `transaction.on_commit` enqueues (most enqueues are deferred to on-commit and won't fire on their own under `django_db`). |
| `deliver_all()` | Deliver every queued task until the queue drains, following retries. Returns the number of attempts. |
| `deliver_next()` | Deliver a single task; returns its `Outcome` (or `None` if the queue is empty). |
| `redeliver_last(task_name=None)` | Re-run the most recently delivered task — an at-least-once duplicate. Pass `task_name` when one trigger fans out into several tasks. |
| `fail_next(n=1)` | Force the next `n` deliveries to fail (transient nack → retry/backoff). |
| `drop_next(n=1)` | Silently lose the next `n` deliveries (the task never runs). |
| `pending()` | How many rows are still queued. |
| `delivered_names()` / `succeeded()` | Introspect what was delivered. |

### Example: a redelivered task must apply its effect exactly once

```python
def test_redelivery_is_idempotent(task_queue, ...):
    with task_queue.capture():
        do_thing_that_enqueues()   # e.g. change a piece of content's cost
    task_queue.deliver_all()       # deliver once
    task_queue.redeliver_last()    # at-least-once duplicate
    assert ...                     # effect applied exactly once
```

### Example: a transient failure retries and then succeeds

```python
def test_recovers_from_transient_failure(task_queue, ...):
    with task_queue.capture():
        do_thing_that_enqueues()
    task_queue.fail_next()         # first delivery nacks
    task_queue.deliver_all()       # backoff → retry → success
    assert ...
```

Worked examples: [`gyrinx/tasks/tests/test_local_backend.py`](../../gyrinx/tasks/tests/test_local_backend.py) and the concurrency chaos tests in [`gyrinx/core/tests/test_task_chaos_concurrency.py`](../../gyrinx/core/tests/test_task_chaos_concurrency.py).

## Run the Dev Server with Async Tasks and Fault Injection

The dev server runs tasks asynchronously in `worker` mode by default. To stress-test idempotency against Pub/Sub-like chaos, set `TASKS_FAULT_*` environment variables before starting it (all default to off):

```bash
# Deliver every task twice (exercise at-least-once idempotency)
TASKS_FAULT_DUPLICATE_RATE=1.0 ./scripts/dev.sh

# 20% of deliveries fail (nack → retry), 5% are dropped, with some latency
TASKS_FAULT_FAILURE_RATE=0.2 \
TASKS_FAULT_DROP_RATE=0.05 \
TASKS_FAULT_LATENCY_SECONDS=0.5 \
./scripts/dev.sh
```

Set `TASKS_FAULT_SEED` to make the injected chaos reproducible, and `TASKS_WORKERS` to change the number of worker threads. See the [reference](../technical-reference/task-framework.md#fault-injection-environment-variables) for the full list.

## Remove a Scheduled Task

### Steps

1. **Remove the task** from `gyrinx/tasks/registry.py`

2. **Deploy** - The orphan cleanup will automatically delete the Cloud Scheduler job

### Notes

- The provisioning system detects and removes orphaned scheduler jobs
- Orphan detection uses the `{env}--gyrinx-scheduler--` prefix to identify managed jobs
- Jobs are only deleted if they match the current environment

## Debug a Failed Task

### Steps

1. **Check Cloud Logging** for the task execution:
   - Filter by `task_name` or `task_id`
   - Look for `task_started`, `task_failed`, `task_completed` events

2. **Check Pub/Sub dead letter queue** (if configured) for messages that exceeded retry limits

3. **Reproduce locally**:

```python
# Get the arguments from the failed message
from n23.core.tasks import my_task

# Call directly to see the full traceback
my_task("arg1", "arg2")
```

1. **Common failure causes**:
   - `429`: Database at capacity — the psycopg connection pool timed out waiting for a connection, or Postgres is out of connection slots (check the pool sizing in `gyrinx/settings_prod.py` and Cloud SQL connection limits)
   - `500`: Unhandled exception (check task code)
   - `400`: Message format issues (check enqueue arguments)
