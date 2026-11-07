# A-08: Deployed release artifact and control

| Metadata | Value |
| --- | --- |
| ID | A-08 |
| Status | Initial baseline; live repository and cloud policies unverified |
| Location and owner | Trusted source, Cloud Build pipeline, container registry image, and Cloud Run service configuration |
| Sensitivity | Internal release configuration; code is public but deploy authority is restricted |
| Integrity need | Critical: a changed image or service configuration controls all application behavior |
| Availability need | High: bad deployments can stop the whole service |
| Flows | [DF-08](../data-flows/deployment.md) |
| Evidence | [build/deploy steps](../../../cloudbuild.yaml), [container startup](../../../docker/entrypoint.sh), [production settings](../../../gyrinx/settings_prod.py) |

## What must be protected

The source revision selected for release, build inputs, produced container image, and Cloud Run image/configuration. Cloud Build builds, pushes, and deploys an image tagged by commit SHA. The container starts application code with the production database and service permissions. The security of this chain depends on source and cloud access controls that are not fully described in the repository.

## Security properties

- Confidentiality: Keep build-time and runtime credentials out of artifacts and logs.
- Integrity: Ensure only reviewed source and authorized build/deploy identities can replace the running image or configuration.
- Availability: Support rollback and prevent a compromised or broken release from blocking all users.
