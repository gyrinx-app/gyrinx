# R-08: Build or deploy authority changes production code

| Metadata | Value |
| --- | --- |
| ID | R-08 |
| Status | Needs deployed-control validation |
| Related threats | [T-09](../threats/t-09-deployment-tampering.md) |
| Assets | [A-08](../assets/a-08-release.md), [A-06](../assets/a-06-service-secrets.md), [A-02](../assets/a-02-player-data.md) |
| Likelihood | Low |
| Impact | Critical |
| Priority | High |
| Confidence | Low for deployed IAM and branch controls; high for the build path |
| Owner | Source protection and cloud deployment |

## Why this rating

The [Cloud Build pipeline](../../../cloudbuild.yaml) builds from source, pushes an image and deploys it to Cloud Run. The [entrypoint](../../../docker/entrypoint.sh) runs migrations before serving. A principal able to alter trusted build input or deployment configuration could run code with application database and storage authority; a malicious migration can persist after rollback. This is a high-consequence privileged path. Branch protection, build service-account IAM and artifact policy are not visible in this repository, so the low likelihood is an assumption awaiting operational review.

## Treatment

Verify branch protection, review requirements, build trigger identity, least-privilege deployment permissions and artifact provenance in the live project. Keep build and deploy records tied to source revisions, and require deliberate migration review. If those controls differ from the assumed state, rerate this risk.
