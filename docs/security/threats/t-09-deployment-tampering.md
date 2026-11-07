# T-09: Modified build input becomes the production application

| Metadata | Value |
| --- | --- |
| ID | T-09 |
| Last reviewed | 2026-11-07 |
| Next review | On material change or by 2027-02-07 |
| STRIDE | Tampering |
| Adversary | [ADV-05: compromised deployment principal](../adversaries/adv-05-deployment-principal.md) |
| Assets | [A-08: release artifact](../assets/a-08-release.md), [A-06: service secrets](../assets/a-06-service-secrets.md), [A-02: player data](../assets/a-02-player-data.md) |
| Data flow / boundary | [DF-08](../data-flows/deployment.md); TB-08, TB-09 and TB-10 |
| Risk | [R-08: deployment](../risk-assessment/r-08-deployment.md) |
| Status | Credible high-impact scenario; repository and cloud access policy not assessed |
| Evidence | [Cloud Build pipeline](../../../cloudbuild.yaml), [container entrypoint](../../../docker/entrypoint.sh), [production settings](../../../gyrinx/settings_prod.py) |

## Scenario

An attacker with write access to the deployment source or build configuration changes application code, dependencies, or the container build step. Cloud Build produces and pushes a new image, then updates Cloud Run to that image. The code runs with the application's database and storage authority and can alter player data, content, or service behavior. Migrations at container startup can make a malicious or mistaken deployment's data change persist after an image rollback.

## Existing controls and uncertainty

The pipeline builds an image tagged by commit SHA and deploys that exact tag; GitHub Actions and Cloud Build provide reviewable records. The repository does not establish branch protection, approval rules, build service-account permissions, or artifact provenance enforcement. This is a boundary and treatment question, not a claim that current source or cloud credentials are compromised.
