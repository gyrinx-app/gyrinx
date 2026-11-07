# DF-06: Background task delivery

| Metadata | Value |
| --- | --- |
| ID | DF-06 |
| Status | Reviewed against production task path |
| Entry point | Task enqueue, Pub/Sub push to /tasks/pubsub/, /tasks/status |
| Actors | Application, Pub/Sub service identity, status reader ([ADV-01](../adversaries/adv-01-anonymous.md)) |
| Assets | [A-07 task state](../assets/a-07-task-state.md), [A-02 player data](../assets/a-02-player-data.md) |
| Trust boundaries | TB-01, TB-02, TB-05 |
| Evidence | [Production task backend](../../../gyrinx/tasks/backend.py), [Shared sender configuration](../../../gyrinx/tasks/config.py), [Push handler](../../../gyrinx/tasks/views.py), [Subscription provisioning](../../../gyrinx/tasks/provisioning.py), [Task executor](../../../gyrinx/tasks/executor.py), [Task invariants](../../../gyrinx/tasks/AGENTS.md) |

## Sequence

~~~mermaid
sequenceDiagram
    actor Reader
    participant App as Django request or scheduler
    participant DB as PostgreSQL
    participant Queue as Google Pub/Sub
    participant Push as /tasks/pubsub/ handler
    App->>DB: Create TaskExecution, crossing TB-02
    App->>Queue: Publish task name and JSON args, crossing TB-05
    Note over App,Queue: TB-05: producer delegates work to asynchronous transport
    Queue->>Push: POST envelope with OIDC bearer token, crossing TB-05
    Note over Queue,Push: TB-05: verify Google token, audience and exact expected sender email
    Push->>DB: Run registered task and persist outcome, crossing TB-02
    Push-->>Queue: 200 ack or retryable failure
    Reader->>Push: GET /tasks/status with group key, crossing TB-01
    Push->>DB: Read status and label only, crossing TB-02
~~~

## Boundaries and controls

| Boundary | From → to | Data and authority crossing | Current control / assumption |
| --- | --- | --- | --- |
| TB-05 | App → Pub/Sub → push handler | Task name, arguments and authority to execute it | Production enqueues registered tasks to per-task topics. Provisioning and the push handler resolve the same expected sender email from TASKS_SERVICE_ACCOUNT or the project-derived default. The handler verifies the Google-signed OIDC token, audience and exact sender email, and rejects requests if it cannot resolve an expected identity. A registry rejects unknown task names. |
| TB-02 | App/worker → database | Execution status and task side effects | Shared executor records lifecycle; tasks must tolerate duplicate and concurrent delivery. |
| TB-01 | Reader → status endpoint | Group key and limited task status | Status endpoint is unauthenticated; group keys are expected to contain an unguessable component. It returns status/label, not arguments or tracebacks. |

## Failure points

- Publish is fire-and-forget: a publish failure is logged after enqueue returns and may lose a requested task.
- Pub/Sub retries may run a task more than once; business idempotency is required per task.
- Deployed Pub/Sub service-account IAM, subscription configuration and runtime identity still require verification outside this repository. Status secrecy depends on group-key entropy.
