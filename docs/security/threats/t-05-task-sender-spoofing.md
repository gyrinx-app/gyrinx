# T-05: Unrelated Google identity reaches task execution

| Metadata | Value |
| --- | --- |
| ID | T-05 |
| STRIDE | Spoofing |
| Adversary | [ADV-01: anonymous caller with a Google service account](../adversaries/adv-01-anonymous.md) |
| Assets | [A-06: service identities](../assets/a-06-service-secrets.md), [A-07: task state](../assets/a-07-task-state.md), [A-02: player data](../assets/a-02-player-data.md) |
| Data flow / boundary | [DF-06](../data-flows/tasks.md); TB-05 |
| Risk | [R-05: task sender](../risk-assessment/r-05-task-sender.md) |
| Status | Mitigated in this branch; live deployment policy unverified |
| Evidence | [task push view](../../../gyrinx/tasks/views.py), [shared identity resolver](../../../gyrinx/tasks/config.py), [subscription provisioning](../../../gyrinx/tasks/provisioning.py), [task routes](../../../gyrinx/tasks/registry.py) |

## Scenario

Previously, an external caller with a Google-signed OIDC token for the Cloud Run audience could be accepted by the push view if TASKS_SERVICE_ACCOUNT was unset. The receiver checked signature and audience but skipped sender identity. A caller able to reach the push URL could name a registered task and supply arguments, causing it to run under application service authority.

## Existing controls and uncertainty

The handler requires POST and a Google-signed audience-bound token. This branch makes provisioning and receiver use the same expected service-account resolver, using an explicit environment value or a project-derived default; the receiver requires the exact email claim and fails closed if no expected identity can be resolved. Focused task tests cover the change. The live Cloud Run IAM policy, service URL, and deployed environment remain to be verified independently.
