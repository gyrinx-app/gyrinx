# Task Framework Reference

This reference documents the complete configuration options, environment variables, and response codes for Gyrinx's background task system.

## TaskRoute Configuration

Declare tasks in the `task_routes` list of the app's own `tasks.py`, using
`TaskRoute`. The platform discovers these lists across all installed apps:

```python
# n23/core/tasks.py
from django.tasks import task

from gyrinx.tasks import TaskRoute

@task
def my_task(): ...

task_routes = [
    TaskRoute(my_task),
]
```

### TaskRoute Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `func` | `Callable` | Required | The task function (decorated with `@task` or raw function) |
| `ack_deadline` | `int` | `300` | Seconds before Pub/Sub retries if no acknowledgement (10-600) |
| `min_retry_delay` | `int` | `10` | Minimum retry backoff in seconds |
| `max_retry_delay` | `int` | `600` | Maximum retry backoff in seconds |
| `schedule` | `str \| None` | `None` | Cron expression for scheduled execution |
| `schedule_timezone` | `str` | `"UTC"` | IANA timezone for the schedule |

### TaskRoute Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Task function name (e.g., `"send_welcome_email"`) |
| `path` | `str` | Full module path (e.g., `"n23.core.tasks.send_welcome_email"`) |
| `topic_name` | `str` | Pub/Sub topic name (e.g., `"prod--gyrinx.tasks--n23.core.tasks.send_welcome_email"`) |
| `scheduler_job_name` | `str` | Cloud Scheduler job name (only for scheduled tasks) |
| `is_scheduled` | `bool` | `True` if a schedule is configured |

### Configuration Examples

```python
# On-demand task with defaults
TaskRoute(send_welcome_email)

# Task with custom retry settings
TaskRoute(
    generate_report,
    ack_deadline=600,       # 10 minutes to complete
    min_retry_delay=30,     # Wait 30s before retry
    max_retry_delay=600,    # Max 10 min backoff
)

# Scheduled task (daily at 3am UTC)
TaskRoute(cleanup_old_data, schedule="0 3 * * *")

# Scheduled task with timezone
TaskRoute(
    send_daily_report,
    schedule="0 9 * * *",
    schedule_timezone="Europe/London"
)
```

## Cron Expression Format

Schedules use standard 5-field cron expressions:

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sunday=0)
│ │ │ │ │
* * * * *
```

### Examples

| Expression | Description |
|------------|-------------|
| `*/10 * * * *` | Every 10 minutes |
| `0 * * * *` | Every hour at minute 0 |
| `0 3 * * *` | Daily at 3:00 AM |
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `0 0 1 * *` | First day of each month at midnight |

## Environment Variables

### Required for Production

| Variable | Description | Example |
|----------|-------------|---------|
| `GCP_PROJECT_ID` | GCP project for Pub/Sub and Scheduler | `gyrinx-prod` |
| `CLOUD_RUN_SERVICE_URL` | Full URL of the Cloud Run service | `https://gyrinx-xyz123-ew.a.run.app` |
| `TASKS_SERVICE_ACCOUNT` | Service account for OIDC verification | `pubsub-invoker@project.iam.gserviceaccount.com` |

### Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TASKS_ENVIRONMENT` | `dev` | Environment prefix for topic/job names (`dev`, `staging`, `prod`) |
| `SCHEDULER_LOCATION` | `europe-west2` | GCP region for Cloud Scheduler |

### Task-Specific Kill Switches

Individual tasks can define their own environment variable kill switches:

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_BACKFILL_SCHEDULER` | `true` | Enable/disable the backfill scheduler task |

## Django Settings

### Base default (settings.py)

```python
TASKS = {
    "default": {
        "BACKEND": "gyrinx.tasks.local_backend.DatabaseBackend",
        "OPTIONS": {"mode": "eager"},
    }
}
TASKS_ENVIRONMENT = os.getenv("TASKS_ENVIRONMENT", "dev")
```

`eager` mode runs tasks inline on enqueue (a drop-in for Django's `ImmediateBackend`), so the test suite stays synchronous.

### Dev server (settings_dev.py)

When `runserver` is on the command line (and not under pytest), the backend switches to `worker` mode so enqueued work runs asynchronously on an in-process thread pool:

```python
TASKS = {
    "default": {
        "BACKEND": "gyrinx.tasks.local_backend.DatabaseBackend",
        "OPTIONS": {
            "mode": "worker",
            "num_workers": int(os.getenv("TASKS_WORKERS", "2")),
        },
    }
}
```

### Production (settings_prod.py)

```python
TASKS = {
    "default": {
        "BACKEND": "gyrinx.tasks.backend.PubSubBackend",
        "OPTIONS": {
            "project_id": GCP_PROJECT_ID,
        },
    }
}
```

## Local backend (DatabaseBackend)

[`DatabaseBackend`](../../gyrinx/tasks/local_backend.py) is the dev/test-only, in-process, durable queue. Production is never routed through it.

### Modes

| Mode | Where | Behaviour |
|------|-------|-----------|
| `eager` | base default / tests | Runs the task inline inside `enqueue()`; no `QueuedTask` row. Drop-in for `ImmediateBackend`. |
| `worker` | dev server (`runserver`) | Persists a `QueuedTask` row; a daemon-thread pool delivers it with retries, backoff, and visibility leases. |
| `manual` | opt-in in tests | Persists a `QueuedTask` row; the `task_queue` fixture drives delivery explicitly. |

### OPTIONS

| Option | Default | Description |
|--------|---------|-------------|
| `mode` | `eager` | One of `eager`, `worker`, `manual`. |
| `num_workers` | `2` | Worker threads in `worker` mode. |
| `lease_seconds` | `300` | Visibility lease; a claimed row is hidden this long before it can be reclaimed. |
| `poll_interval` | `1.0` | Seconds a worker waits between queue polls. |
| `max_attempts` | `5` | Delivery attempts before a task is given up. |
| `faults` | from env | Fault-injection config (see below). |

### Fault-injection environment variables

Read by `worker` mode (dev server), off by default. All rates are in `[0, 1]`.

| Variable | Default | Effect |
|----------|---------|--------|
| `TASKS_FAULT_DUPLICATE_RATE` | `0` | Chance a successful delivery is redelivered once (at-least-once duplicate). |
| `TASKS_FAULT_FAILURE_RATE` | `0` | Chance a delivery fails (nack → retry with backoff). |
| `TASKS_FAULT_DROP_RATE` | `0` | Chance a delivery is silently lost (never runs). |
| `TASKS_FAULT_LATENCY_SECONDS` | `0` | Fixed delay added before each delivery. |
| `TASKS_FAULT_LATENCY_JITTER` | `0` | Extra uniform-random delay in `[0, jitter)`. |
| `TASKS_FAULT_SEED` | (none) | Seed the fault RNG for reproducible chaos. |
| `TASKS_WORKERS` | `2` | Number of worker threads on the dev server. |

### QueuedTask model

In `worker`/`manual` mode a task is a durable row in `QueuedTask` (`gyrinx/tasks/models.py`), claimed with `SELECT … FOR UPDATE SKIP LOCKED` under a visibility lease so an interrupted delivery is redelivered rather than lost. Key fields:

| Field | Description |
|-------|-------------|
| `task_id` | Matches `TaskExecution.task_id` (the Django `TaskResult.id`). |
| `task_name` | Registered task name to resolve and run. |
| `args` / `kwargs` | JSON-serialised call arguments. |
| `available_at` | Earliest delivery time (set forward for deferred tasks and retry backoff). |
| `attempts` / `max_attempts` | Delivery-attempt counter and give-up threshold. |
| `locked_until` / `locked_by` | Visibility lease: while set and in the future, the row is hidden from other workers. |
| `last_error` | Error from the most recent failed attempt. |

## HTTP Response Codes

The push handler (`/tasks/pubsub/`) returns these status codes:

| Code | Meaning | Pub/Sub Behavior |
|------|---------|------------------|
| `200` | Task completed successfully | Message acknowledged |
| `400` | Bad request (malformed message, unknown task) | Message acknowledged (prevents infinite retry) |
| `403` | OIDC token verification failed | Message not acknowledged |
| `429` | Database connection pool exhausted | Message not acknowledged (retry with backoff) |
| `500` | Task raised an exception | Message not acknowledged (retry with backoff) |

## Resource Naming Conventions

### Pub/Sub Topics

Format: `{env}--gyrinx.tasks--{module.path.task_name}`

Example: `prod--gyrinx.tasks--n23.core.tasks.send_welcome_email`

### Pub/Sub Subscriptions

Format: `{topic_name}-sub`

Example: `prod--gyrinx.tasks--n23.core.tasks.send_welcome_email-sub`

### Cloud Scheduler Jobs

Format: `{env}--gyrinx-scheduler--{module-path-task_name}`

Example: `prod--gyrinx-scheduler--gyrinx-core-tasks-cleanup_old_data`

Note: Dots in the module path are replaced with hyphens because Cloud Scheduler job names only allow `[a-zA-Z0-9_-]`.

## Message Payload Format

Messages published to Pub/Sub follow this JSON schema:

```json
{
  "task_id": "uuid-string",
  "task_name": "function_name",
  "args": [],
  "kwargs": {},
  "enqueued_at": "2024-01-15T10:30:00+00:00"
}
```

For scheduled tasks, `task_id` is prefixed with `scheduled-` and `enqueued_at` is omitted.

## Backend Capabilities

The `PubSubBackend` has the following capability flags:

| Capability | Supported | Notes |
|------------|-----------|-------|
| `supports_defer` | No | To implement, use Pub/Sub scheduled delivery |
| `supports_async_task` | No | To implement, use async Pub/Sub client |
| `supports_get_result` | Yes | Results stored in `TaskExecution` model |
| `supports_priority` | No | Unclear |

`DatabaseBackend` (dev/tests) additionally sets `supports_defer = True` (deferred delivery via `QueuedTask.available_at`) and `supports_get_result = True` (reading back the `TaskExecution` row).

## Task Execution Tracking

Tasks are tracked via the `TaskExecution` model with a state machine for lifecycle management:

- **READY**: Task enqueued, waiting to run
- **RUNNING**: Task currently executing
- **SUCCESSFUL**: Task completed successfully (result stored in `return_value`)
- **FAILED**: Task raised an exception (error stored in `error_message`, `error_traceback`)

See [State Machine Reference](state-machine.md) for details on the state machine pattern.
