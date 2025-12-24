# Task Framework Architecture

This document explains the design decisions, message flow, and infrastructure provisioning strategy for Gyrinx's background task system.

## Why Pub/Sub?

We chose Google Cloud Pub/Sub over alternatives for several reasons:

### Compared to Celery

- **No broker to manage**: Pub/Sub is fully managed. Celery requires running Redis or RabbitMQ.
- **Native GCP integration**: Works seamlessly with Cloud Run, Cloud Scheduler, and IAM.
- **Cost-effective**: Pay per message, no idle infrastructure costs.
- **Simpler deployment**: No separate worker processes to manage.

### Compared to Cloud Tasks

- **More flexible retry policies**: Pub/Sub offers configurable exponential backoff.
- **Better observability**: Native integration with Cloud Monitoring and Logging.
- **Easier local development**: Messages are just HTTP POSTs; easy to test without emulators.

### Compared to Django Q / Huey

- **Production-grade reliability**: Google's SLA-backed infrastructure.
- **No database polling**: Push-based delivery is more efficient.
- **Scales automatically**: No worker pool sizing decisions.

### Trade-offs

- **Fire-and-forget publishing**: We don't wait for Pub/Sub confirmation to keep request latency low. This means message loss is theoretically possible on network failures, though rare in practice.
- **No result storage**: Unlike Celery, we don't store task results. Tasks that need to report results should write to the database directly.
- **No task priorities**: All tasks use the same delivery mechanism. For true priority support, we would need separate topics.

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

1. **Enqueue**: Python code calls `task.enqueue(...)` with arguments
2. **Publish**: `PubSubBackend.enqueue()` serialises arguments to JSON and publishes to the task-specific topic
3. **Deliver**: The push subscription sends an HTTP POST to `/tasks/pubsub/` with the message
4. **Verify**: The handler verifies the OIDC token to ensure the request came from Pub/Sub
5. **Route**: The handler looks up the task by `task_name` in the registry
6. **Execute**: The task function runs with the deserialised arguments
7. **Acknowledge**: HTTP 200 acknowledges the message; other codes trigger retry

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

This design means scheduled and on-demand invocations use the same code path, simplifying testing and debugging.

## Infrastructure Provisioning

### When Does Provisioning Run?

Provisioning runs automatically during Cloud Run startup when the `K_SERVICE` environment variable is present. This variable is set automatically by Cloud Run.

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

For each task in the registry:

1. **Pub/Sub Topic**: `{env}--gyrinx.tasks--{module.path.task_name}`
2. **Push Subscription**: Points to `/tasks/pubsub/` with OIDC authentication
3. **Cloud Scheduler Job** (if scheduled): Publishes to the topic on the cron schedule

### Idempotency

Provisioning is idempotent - it's safe to run on every startup:

- Topics: Created if missing, skipped if exists
- Subscriptions: Created if missing, **updated** if exists (to apply config changes)
- Scheduler jobs: Created if missing, **updated** if exists

This means you can change retry policies or schedules, and the new configuration is applied on the next deployment.

### Orphan Cleanup

When you remove a scheduled task from the registry, the system automatically deletes the corresponding Cloud Scheduler job:

1. List all jobs with our naming prefix
2. Compare against current scheduled tasks
3. Delete jobs that no longer have a matching task

This prevents stale scheduled jobs from continuing to run after a task is removed.

## Security Model

### OIDC Authentication

Push subscriptions use OIDC tokens to authenticate requests:

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

### Backpressure: The 429 Pattern

When the database connection pool is exhausted, returning 500 would cause rapid retries that worsen the problem. Instead, we return 429:

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

Each task can configure:

- `ack_deadline`: How long before Pub/Sub assumes the task failed (10-600 seconds)
- `min_retry_delay`: Minimum wait before retry
- `max_retry_delay`: Maximum wait (caps exponential backoff)

Pub/Sub uses exponential backoff between min and max delay, doubling the wait time on each retry up to the maximum.

## Development vs Production

| Aspect | Development | Production |
|--------|-------------|------------|
| Backend | `ImmediateBackend` (sync) | `PubSubBackend` (async) |
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

### Priority Queues

For true priority support:

1. Create separate topics per priority level
2. Configure different subscription throughput limits
3. Route tasks based on priority parameter

### Dead Letter Queues

Pub/Sub supports dead letter topics for messages that exceed retry limits. This would:

1. Create a dead letter topic per task
2. Configure max delivery attempts
3. Allow inspection/replay of failed messages
