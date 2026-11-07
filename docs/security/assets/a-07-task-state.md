# A-07: Task and webhook records

| Metadata | Value |
| --- | --- |
| ID | A-07 |
| Status | Initial baseline |
| Location and owner | TaskExecution and WebhookRequest in the application database; Pub/Sub transport in production |
| Sensitivity | Internal; payloads may contain personal data or short-lived provider tokens |
| Integrity need | High: forged or altered task state can trigger domain writes or misstate results |
| Availability need | Medium to high: campaign operations and integrations depend on delivery |
| Flows | [DF-06](../data-flows/tasks.md), [DF-07](../data-flows/integrations.md) |
| Evidence | [task model](../../../gyrinx/tasks/models.py), [task push and status views](../../../gyrinx/tasks/views.py), [webhook model](../../../gyrinx/api/models.py), [Discord task arguments](../../../gyrinx/api/tasks.py) |

## What must be protected

Queued commands, task arguments and results, failures and tracebacks, and stored external webhook payloads. TaskExecution persists args and kwargs as JSON and full error tracebacks; the Discord issue task accepts an interaction token and message content. The unauthenticated group-status endpoint deliberately returns only status and labels when given a group key.

## Security properties

- Confidentiality: Keep raw payloads, task arguments, and tracebacks within operational access; do not return them from public status endpoints.
- Integrity: Authenticate task delivery and preserve idempotent processing because messages can be delivered more than once.
- Availability: Bound retry and failure behavior so essential background writes can complete.
