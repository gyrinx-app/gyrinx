# infra/

Terraform definitions for Gyrinx's GCP infrastructure.

> ⚠️ **Status: experimental.** Nothing here has been applied to production. The
> existing prod project (`windy-ellipse-440618-p9`) was built click-ops. This tree
> is designed to be validated end-to-end against a fresh `staging` project first,
> then — only once we're confident — adopted in prod by importing existing
> resources into state.

## Layout

```
infra/
  modules/
    bootstrap/      # Resources that must exist before the main module can plan:
                    #   GCS state bucket, enabled APIs, Artifact Registry, the
                    #   Terraform service account itself. Run by a human, local state.
    gyrinx/         # The application stack: Cloud Run, Cloud SQL, GCS uploads
                    # bucket, CDN, Secret Manager shells, IAM. One module, multiple
                    # env wrappers.
  environments/
    prod/           # Wrapper for the existing prod project.
    staging/        # Wrapper for the (to-be-created) staging project. This is
                    # what we use to validate the modules.
```

See `infra/modules/bootstrap/README.md` and `infra/modules/gyrinx/README.md`
for module-level docs.

## Mental model (cribbed from the layered guide)

- **Bootstrap** is "who can change what" and "where state lives." Local state.
- **Main module** is the application shape. Each env is a thin wrapper.
- **Application config** (env var values, secret values, image SHAs) is *not*
  in Terraform. Secrets are TF-managed shells; values are populated out of band.
  Cloud Run images come from Cloud Build; TF uses a placeholder and ignores
  `template`/`scaling` drift.

## Workflow (staging end-to-end)

1. Manually create the GCP project `gyrinx-staging` and link billing.
2. From `infra/modules/bootstrap`, with local state:
   - `terraform init`
   - `terraform apply -var-file=../../environments/staging/bootstrap.tfvars`
3. From `infra/environments/staging`:
   - `terraform init` (uses the GCS backend bucket created by bootstrap)
   - `terraform plan` → iterate until clean
   - `terraform apply` (only once confident)

## Workflow (prod adoption — future)

1. From `infra/modules/bootstrap`, apply against the prod project.
2. From `infra/environments/prod`, import each existing resource with
   `terraform import`. Plan should converge to no-op.
3. Once plan is empty, prod is under management.
