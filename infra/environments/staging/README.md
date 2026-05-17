# staging environment

Wrapper around `../../modules/gyrinx` configured for the
`gyrinx-staging` GCP project. **Managed by Spacelift** (stack
`gyrinx-staging` — created by `infra/bootstrap/`).

State is stored by Spacelift; this directory has no backend.tf.

## How runs happen

- A push to `main` that touches `infra/environments/staging/**` or
  `infra/modules/**` triggers a plan in the Spacelift stack.
- `autodeploy = false` by default — you confirm the apply in the UI.
- The runner authenticates to GCP via the long-lived SA key mounted
  on the stack at `/mnt/workspace/gcp-credentials.json`.

## Local plan (debugging)

You can run `terraform plan` locally if you set ADC to a credential
that has equivalent rights in the staging project — useful for
iterating on module changes before pushing. Don't `apply` locally;
let Spacelift do that so the state stays consistent.

## Differences from prod

- Smaller Cloud SQL tier (`db-f1-micro`, zonal, no backups).
- Cloud Run scale capped low.
- Uploads bucket has `force_destroy = true`.
- CDN load balancer disabled (no `cdn.gyrinx-staging` DNS to point at it).
