# R-05: Task push could accept an unintended sender

| Metadata | Value |
| --- | --- |
| ID | R-05 |
| Last reviewed | 2026-11-07 |
| Next review | On deployment verification or by 2027-02-07 |
| Status | Control implemented; deployment verification pending |
| Related threats | [T-05](../threats/t-05-task-sender-spoofing.md) |
| Assets | [A-06](../assets/a-06-service-secrets.md), [A-07](../assets/a-07-task-state.md), [A-02](../assets/a-02-player-data.md) |
| Likelihood | Low after fix |
| Impact | Critical |
| Priority | Medium after fix |
| Confidence | High for code behavior; low for deployed IAM and configuration |
| Owner | Task delivery and deployment configuration |

## Why this rating

The previous [task receiver](../../../gyrinx/tasks/views.py) checked a Google-signed audience token but compared its sender email only when TASKS_SERVICE_ACCOUNT was configured, while [provisioning](../../../gyrinx/tasks/provisioning.py) had its own project-derived default. Without that setting, an unintended principal with a valid audience token could have dispatched a registered task with application authority. The repository does not show the live environment value or external invocation policy, so this was a conditional path rather than a demonstrated production exploit. The possible consequence spans task-driven writes.

## Treatment

This PR makes provisioning and the receiver share [one expected identity resolver](../../../gyrinx/tasks/config.py): an explicit service account or the same project-derived default. The receiver now requires an exact sender email and fails closed without an expected identity; tests cover the default, override, mismatch and missing-identity cases. Verify the live Pub/Sub subscription sender, Cloud Run ingress/IAM and runtime variables before deployment. Audience and signature checks remain in place.
