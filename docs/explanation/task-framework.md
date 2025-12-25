# Task Framework Architecture

This document explains the design decisions, message flow, and infrastructure provisioning strategy for Gyrinx's background task system.

The basic concepts from Tasks are new in Django 6.0. We have a Pub/Sub backend for asynchronous execution, with support for scheduled tasks via Cloud Scheduler. The [`TaskRoute`](../../gyrinx/tasks/route.py) is custom to Gyrinx, providing configuration options for retries and scheduling.

## Why Pub/Sub?

We like using Google Cloud Platform built-ins in general. Pub/Sub is fully managed, and works well with Cloud Run (pushing to an endpoint), Cloud Scheduler, and IAM. It's fairly cost-effective per message, with no idle infrastructure costs, and we don't have separate worker processes to manage.

## How we use Pub/Sub

- Fire-and-forget publishing: We don't wait for Pub/Sub confirmation to keep request latency low. This means message loss is theoretically possible on network failures. We could introduce silent retries in the future. See [`PubSubBackend.enqueue()`](../../gyrinx/tasks/backend.py).
- No result storage: For now, tasks that need to report results should write to the database directly.
- No task priorities: All tasks use the same delivery mechanism. For true priority support, we'd need separate topics.

## Message Flow

### On-Demand Task Execution

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Python Code    │     │    Pub/Sub      │     │   Cloud Run     │
│                 │     │                 │     │                 │
│  task.enqueue() ├────►│  Topic          ├────►│  /tasks/pubsub/ │
│                 │     │      │          │     │        │        │
└─────────────────┘     │      ▼          │     │        ▼        │
                        │  Subscription   │     │  Task Function  │
                        │  (push)         │     │                 │
                        └─────────────────┘     └─────────────────┘
```

1. Enqueue: Python code calls `task.enqueue(...)` with arguments
2. Publish: [`PubSubBackend.enqueue()`](../../gyrinx/tasks/backend.py) serialises arguments to JSON and publishes to the task-specific topic
3. Deliver: The push subscription sends an HTTP POST to `/tasks/pubsub/` with the message
4. Verify: The handler verifies the OIDC token to ensure the request came from Pub/Sub (see [`_verify_oidc_token()`](../../gyrinx/tasks/views.py))
5. Route: The handler looks up the task by `task_name` in the [registry](../../gyrinx/tasks/registry.py)
6. Execute: The task function runs with the deserialised arguments
7. Acknowledge: HTTP 200 acknowledges the message; other codes trigger retry

The push handler is [`pubsub_push_handler()`](../../gyrinx/tasks/views.py).

### Scheduled Task Execution

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Cloud Scheduler │     │    Pub/Sub      │     │   Cloud Run     │
│                 │     │                 │     │                 │
│  Cron trigger   ├────►│  Topic          ├────►│  /tasks/pubsub/ │
│                 │     │      │          │     │        │        │
└─────────────────┘     │      ▼          │     │        ▼        │
                        │  Subscription   │     │  Task Function  │
                        │  (push)         │     │                 │
                        └─────────────────┘     └─────────────────┘
```

Scheduled tasks work identically to on-demand tasks, except:

1. Cloud Scheduler triggers based on the cron expression
2. Scheduler publishes a pre-configured message to the same topic
3. The rest of the flow is identical

This design means scheduled and on-demand invocations use the same code path.

## Infrastructure Provisioning

### When Does Provisioning Run?

Provisioning runs automatically during Cloud Run startup when the `K_SERVICE` environment variable is present. Cloud Run sets this automatically. See [`TasksConfig.ready()`](../../gyrinx/tasks/apps.py).

```python
# In gyrinx/tasks/apps.py
def ready(self):
    if not os.getenv("K_SERVICE"):
        return  # Skip outside Cloud Run

    provision_task_infrastructure()
```

Provisioning is skipped during:

- Local development (no `K_SERVICE`)
- Migration commands
- Test runs

### What Gets Provisioned?

For each task in the [registry](../../gyrinx/tasks/registry.py), [`provision_task_infrastructure()`](../../gyrinx/tasks/provisioning.py) creates:

1. Pub/Sub Topic: `{env}--gyrinx.tasks--{module.path.task_name}`
2. Push Subscription: Points to `/tasks/pubsub/` with OIDC authentication
3. Cloud Scheduler Job (if scheduled): Publishes to the topic on the cron schedule

### Idempotency

Provisioning is (in theory!) idempotent—it's safe to run on every startup:

- Topics: Created if missing, skipped if exists
- Subscriptions: Created if missing, **updated** if exists (to apply config changes)
- Scheduler jobs: Created if missing, **updated** if exists

This means you can change retry policies or schedules, and the new configuration is applied on the next deployment.

### Orphan Cleanup

When you remove a scheduled task from the registry, the system automatically deletes the corresponding Cloud Scheduler job. See [`_cleanup_orphaned_scheduler_jobs()`](../../gyrinx/tasks/provisioning.py):

1. List all jobs with our naming prefix
2. Compare against current scheduled tasks
3. Delete jobs that no longer have a matching task

This prevents stale scheduled jobs from continuing to run after a task is removed.

## Security Model

### OIDC Authentication

Push subscriptions use OIDC tokens to authenticate requests. See [`_verify_oidc_token()`](../../gyrinx/tasks/views.py):

```
Pub/Sub → POST /tasks/pubsub/
          Authorization: Bearer <OIDC token>
```

The handler verifies:

1. The token signature (signed by Google)
2. The audience matches `CLOUD_RUN_SERVICE_URL`
3. The service account email matches `TASKS_SERVICE_ACCOUNT` (optional)

In development (`DEBUG=True`), OIDC verification is skipped for convenience.

### Why Not Use Pub/Sub Pull?

Pull subscriptions require the application to poll for messages. This doesn't work well with Cloud Run's scale-to-zero model:

- Cloud Run instances can be terminated when idle
- No background polling possible
- Would require always-on worker instances

Push subscriptions solve this by having Pub/Sub make HTTP requests, which naturally triggers Cloud Run to scale up.

## Error Handling and Retries

### Response Code Semantics

| Code | Meaning | Retry? |
|------|---------|--------|
| 200 | Success | No (message acknowledged) |
| 400 | Permanent failure | No (prevents infinite retry) |
| 403 | Auth failure | No |
| 429 | Capacity exceeded | Yes (exponential backoff) |
| 500 | Transient failure | Yes (exponential backoff) |

### Backpressure

When the database connection pool is exhausted, returning 500 would cause rapid retries that worsen the problem. Instead, we [return 429](../../gyrinx/tasks/views.py):

```python
try:
    connection.ensure_connection()
except OperationalError as e:
    if "connection slots" in str(e):
        return HttpResponse("Database at capacity", status=429)
    raise
```

Pub/Sub treats 429 like other retriable errors, applying exponential backoff. This gives the database time to recover.

### Retry Policy

Each task can configure via [`TaskRoute`](../../gyrinx/tasks/route.py):

- `ack_deadline`: How long before Pub/Sub assumes the task failed (10–600 seconds)
- `min_retry_delay`: Minimum wait before retry
- `max_retry_delay`: Maximum wait (caps exponential backoff)

Pub/Sub uses exponential backoff between min and max delay, doubling the wait time on each retry up to the maximum.

## Development vs Production

| Aspect | Development | Production |
|--------|-------------|------------|
| Backend | `ImmediateBackend` (sync) | [`PubSubBackend`](../../gyrinx/tasks/backend.py) (async) |
| OIDC verification | Skipped | Enforced |
| Provisioning | Skipped | Automatic on startup |
| Topic naming | `dev--gyrinx.tasks--...` | `prod--gyrinx.tasks--...` |

In development, `task.enqueue()` calls the task function immediately and synchronously. This makes debugging straightforward but doesn't test the async behaviour.

## Future Considerations

### Deferred Execution

Pub/Sub supports scheduled message delivery. We could add:

```python
task.enqueue(..., run_after=timedelta(hours=1))
```

This would set the `publishTime` attribute on the message.

### Task Results

Currently tasks are fire-and-forget. To support `task.get_result()`:

1. Store results in the database or Cloud Storage
2. Implement `get_result()` in the backend
3. Consider result expiry/cleanup

### Dead Letter Queues

Pub/Sub supports dead letter topics for messages that exceed retry limits. This would:

1. Create a dead letter topic per task
2. Configure max delivery attempts
3. Allow inspection/replay of failed messages
