# R-07: Impersonated edits lack direct operator attribution

| Metadata | Value |
| --- | --- |
| ID | R-07 |
| Status | Open |
| Related threats | [T-07](../threats/t-07-impersonation-attribution.md) |
| Assets | [A-01](../assets/a-01-accounts.md), [A-02](../assets/a-02-player-data.md) |
| Likelihood | Medium |
| Impact | Medium |
| Priority | Medium |
| Confidence | Medium |
| Owner | Impersonation and audit history |

## Why this rating

The [impersonation middleware](../../../gyrinx/middleware.py) swaps request.user to the target, so a normal history entry or action ledger can name the player even when a superuser made the edit. [ImpersonationLog](../../../gyrinx/site/models.py) keeps the operator and session window, which gives a possible time-based investigation path, but there is no direct action-to-session link in the inspected model. Legitimate support impersonation can therefore create ambiguous audit records without any attacker first compromising the deployment. The effect is limited to privileged sessions and incident reconstruction, rather than general data access.

## Treatment

Attach the impersonating operator and impersonation session ID to security-relevant audit events or history context for writes made during an overlay. Test that ordinary user edits and impersonated edits remain distinguishable. Preserve the start/stop log and superuser-only control.
