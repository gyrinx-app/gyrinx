# STRIDE threat inventory

| Metadata | Value |
| --- | --- |
| Scope | Material actions or events at the boundaries in the [data-flow index](../data-flows/index.md) |
| Method | One primary STRIDE category per scenario; code-backed controls and uncertainty in each file |
| Status | First pass; likelihood and impact in [risk assessment](../risk-assessment/index.md) |
| Exclusions | Marginal outcomes and duplicate downstream effects are not separate threats |

STRIDE means **Spoofing** identity, **Tampering** with data or code, **Repudiation** of an action, **Information Disclosure**, **Denial of Service**, and **Elevation of Privilege**. A threat is a plausible path to direct harm, not necessarily a demonstrated exploit.

| ID | Primary category | Scenario | Evidence state |
| --- | --- | --- | --- |
| [T-01](t-01-staff-authoring-auth.md) | Spoofing | Password-only staff session can reach N26 authoring | Observed gate difference |
| [T-02](t-02-cross-owner-write.md) | Elevation of Privilege | A player write acts on another player's object | Credible regression scenario |
| [T-03](t-03-active-upload.md) | Tampering | Player stores active SVG through TinyMCE | Mitigated in this branch |
| [T-04](t-04-held-sheet-disclosure.md) | Information Disclosure | Held authoring CSV is read from public storage | Public read remains |
| [T-05](t-05-task-sender-spoofing.md) | Spoofing | An unrelated Google identity invokes a background task | Mitigated in this branch |
| [T-06](t-06-public-read-overload.md) | Denial of Service | Automated public reads exhaust serving capacity | Prior incident; mitigations exist |
| [T-07](t-07-impersonation-attribution.md) | Repudiation | A privileged edit is attributed only to the impersonated user | Observed audit design |
| [T-08](t-08-shared-read-privacy.md) | Information Disclosure | A shared read exposes owner-only gang information | Credible regression scenario |
| [T-09](t-09-deployment-tampering.md) | Tampering | Modified build input becomes the production application | Credible source-to-runtime scenario |

## Coverage by flow

A dash means the category was screened and no independent material scenario was retained; it does not mean the flow was unreviewed. Cells link to the same threat where it crosses more than one flow. Provider signatures in DF-07 yielded no separate material threat in this pass; task delivery is covered by T-05 in DF-06.

| Flow | Spoofing | Tampering | Repudiation | Information Disclosure | Denial of Service | Elevation of Privilege |
| --- | --- | --- | --- | --- | --- | --- |
| [DF-01](../data-flows/account-session.md) Account/session | [T-01](t-01-staff-authoring-auth.md) | — | [T-07](t-07-impersonation-attribution.md) | — | — | — |
| [DF-02](../data-flows/player-writes.md) Player writes | — | — | [T-07](t-07-impersonation-attribution.md) | — | — | [T-02](t-02-cross-owner-write.md) |
| [DF-03](../data-flows/shared-reads.md) Shared reads | — | — | — | [T-08](t-08-shared-read-privacy.md) | [T-06](t-06-public-read-overload.md) | — |
| [DF-04](../data-flows/staff-authoring.md) Staff authoring | [T-01](t-01-staff-authoring-auth.md) | — | — | [T-04](t-04-held-sheet-disclosure.md) | — | — |
| [DF-05](../data-flows/media.md) Media | — | [T-03](t-03-active-upload.md) | — | [T-04](t-04-held-sheet-disclosure.md) | — | — |
| [DF-06](../data-flows/tasks.md) Tasks | [T-05](t-05-task-sender-spoofing.md) | — | — | — | — | — |
| [DF-07](../data-flows/integrations.md) Integrations | — | — | — | — | — | — |
| [DF-08](../data-flows/deployment.md) Deployment | — | [T-09](t-09-deployment-tampering.md) | — | — | — | — |

T-02 and T-08 are control-sensitive scenarios, not observed authorization failures. Their risk assessment uses residual likelihood after current controls.
