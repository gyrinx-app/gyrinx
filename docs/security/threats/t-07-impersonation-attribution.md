# T-07: An impersonated edit is attributed to the target

| Metadata | Value |
| --- | --- |
| ID | T-07 |
| STRIDE | Repudiation |
| Adversary | [ADV-04: compromised staff identity](../adversaries/adv-04-staff-session.md) |
| Assets | [A-02: player data and history](../assets/a-02-player-data.md), [A-01: account identity](../assets/a-01-accounts.md) |
| Data flow / boundary | [DF-01](../data-flows/account-session.md) and [DF-02](../data-flows/player-writes.md); TB-06 |
| Risk | [R-07: impersonation audit](../risk-assessment/r-07-impersonation-audit.md) |
| Status | Observed attribution design; practical audit impact needs validation |
| Evidence | [impersonation middleware](../../../gyrinx/middleware.py), [impersonation log](../../../gyrinx/site/models.py), [start and stop views](../../../gyrinx/views_impersonation.py) |

## Scenario

A superuser impersonates a player and changes a gang or campaign. The middleware deliberately replaces request.user with the target, so ordinary history and action ledgers record the target as actor. The operator can later deny having made a specific edit, while the apparent player can deny it too. This impedes incident reconstruction if no per-action link to the impersonation session is retained.

## Existing controls and uncertainty

Only superusers can start an overlay; the start and stop views require login, POST and CSRF. ImpersonationLog records operator, target and session window, and the middleware keeps request.impersonator during each request. A timestamp correlation may identify the operator, but the inspected model does not carry a direct action-to-impersonation-log relationship. Whether request logs retain that relation requires separate validation.
