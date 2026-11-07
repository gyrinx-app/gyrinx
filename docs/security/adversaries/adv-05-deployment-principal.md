# ADV-05: Compromised deployment principal

| Metadata | Value |
| --- | --- |
| ID | ADV-05 |
| Status | Initial baseline |
| Starting access | Control of a source branch accepted by the deployment trigger, the build identity, or a cloud identity allowed to update Cloud Run |
| Reachable boundaries | TB-07 source/build to runtime; TB-02 runtime to database; TB-03 runtime to storage; TB-05 runtime to task transport |
| Assets sought | [A-01](../assets/a-01-accounts.md), [A-02](../assets/a-02-player-data.md), [A-06](../assets/a-06-service-secrets.md), [A-07](../assets/a-07-task-state.md), [A-08](../assets/a-08-release.md) |
| Evidence / assumption | [deployment pipeline](../../../cloudbuild.yaml), [deployment description](../../deployment.md), [production settings](../../../gyrinx/settings_prod.py) |

## Goals and capabilities

A principal who can replace the image built and deployed from trusted source, or update the Cloud Run service directly, can run code with the application's database, storage, and integration permissions. The code-based model treats this as a high-impact compromise path; it does not assert that current branch protection or IAM is weak.

## Limits

This actor is distinct from an ordinary player or staff author. Its starting credential is a source or cloud deployment authority. Live branch protection, build trigger permissions, workload identity, and cloud IAM need operational verification before likelihood can be rated confidently.
