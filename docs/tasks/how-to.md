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
    from gyrinx.core.models import User

    user = User.objects.get(pk=user_id)
    # ... send notification logic
```

1. **Register the task** in `gyrinx/tasks/registry.py`:

```python
from gyrinx.core.tasks import send_notification

def _get_tasks() -> list[TaskRoute]:
    global _tasks
    if _tasks is None:
        from gyrinx.core.tasks import (
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
from gyrinx.core.tasks import send_notification

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

1. **Check an environment variable** at the start of your task:

```python
import os
from django.tasks import task

@task
def expensive_batch_job():
    if os.getenv("ENABLE_BATCH_JOB", "true").lower() != "true":
        logger.info("Batch job disabled via ENABLE_BATCH_JOB")
        return

    # ... rest of task
```

1. **Document the variable** in `docs/deployment-environment-variables.md` and this reference.

1. **Disable in production** by setting the environment variable:

```bash
# In Cloud Run environment variables
ENABLE_BATCH_JOB=false
```

### Notes

- Default to enabled (`"true"`) for backwards compatibility
- Log when the kill switch is active for observability
- Use descriptive variable names: `ENABLE_<TASK_NAME>`

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

### Prerequisites

- Development environment running
- Task registered in registry

### Steps

1. **In development, tasks run immediately** (no Pub/Sub):

```python
# In Django shell
from gyrinx.core.tasks import hello_world

# This runs synchronously in development
hello_world.enqueue(name="Developer")
```

1. **To test the actual task function**:

```python
# Call the underlying function directly
from gyrinx.core.tasks import refresh_list_facts

refresh_list_facts("list-uuid-here")
```

1. **To test with Pub/Sub locally**, you would need to:
   - Set up a local Pub/Sub emulator
   - Configure the backend to use it
   - This is not typically necessary for development

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
from gyrinx.core.tasks import my_task

# Call directly to see the full traceback
my_task("arg1", "arg2")
```

1. **Common failure causes**:
   - `429`: Database connection pool exhausted (check `CONN_MAX_AGE`, connection limits)
   - `500`: Unhandled exception (check task code)
   - `400`: Message format issues (check enqueue arguments)

## Monitor Task Health

### Metrics to Track

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Task success rate | `track("task_completed")` / `track("task_started")` | <95% |
| Task latency | Time between `enqueued_at` and completion | p95 > 5min |
| Dead letter queue depth | Pub/Sub metrics | >0 |
| Database connection errors | `track("task_failed")` with connection errors | Any |

### Using track() Events

The task system emits these tracking events:

- `task_published` - Message sent to Pub/Sub
- `task_publish_failed` - Failed to publish
- `task_started` - Handler received message
- `task_completed` - Task finished successfully
- `task_failed` - Task raised exception
