# Task Framework Reference

This reference documents the complete configuration options, environment variables, and response codes for Gyrinx's background task system.

## TaskRoute Configuration

Register tasks in `gyrinx/tasks/registry.py` using `TaskRoute`:

```python
from gyrinx.tasks import TaskRoute
from gyrinx.core.tasks import my_task

tasks = [
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
| `path` | `str` | Full module path (e.g., `"gyrinx.core.tasks.send_welcome_email"`) |
| `topic_name` | `str` | Pub/Sub topic name (e.g., `"prod--gyrinx.tasks--gyrinx.core.tasks.send_welcome_email"`) |
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

### Development (settings.py)

```python
TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
    }
}
TASKS_ENVIRONMENT = os.getenv("TASKS_ENVIRONMENT", "dev")
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

Example: `prod--gyrinx.tasks--gyrinx.core.tasks.send_welcome_email`

### Pub/Sub Subscriptions

Format: `{topic_name}-sub`

Example: `prod--gyrinx.tasks--gyrinx.core.tasks.send_welcome_email-sub`

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
| `supports_defer` | No | Would require Pub/Sub scheduled delivery |
| `supports_async_task` | No | Would require async Pub/Sub client |
| `supports_get_result` | No | Would require result storage (database/Cloud Storage) |
| `supports_priority` | No | Would require separate topics per priority |

## File Locations

| File | Purpose |
|------|---------|
| `gyrinx/tasks/__init__.py` | Package exports (`TaskRoute`) |
| `gyrinx/tasks/route.py` | `TaskRoute` dataclass definition |
| `gyrinx/tasks/registry.py` | Task registration (add tasks here) |
| `gyrinx/tasks/backend.py` | `PubSubBackend` implementation |
| `gyrinx/tasks/views.py` | Push handler view |
| `gyrinx/tasks/provisioning.py` | Auto-provisioning logic |
| `gyrinx/tasks/apps.py` | Django app config (triggers provisioning) |
| `gyrinx/tasks/urls.py` | URL routing |
| `gyrinx/core/tasks.py` | Task function implementations |
