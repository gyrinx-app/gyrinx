# infra/

Terraform definitions for Gyrinx's GCP infrastructure, run on
[Spacelift](https://spacelift.io/) (free tier).

> ⚠️ **Status: experimental.** Nothing here has been applied to
> production. The existing prod project (`windy-ellipse-440618-p9`)
> was built click-ops. This tree is designed to be validated end-to-
> end against a fresh `gyrinx-staging` project first, then — only
> once we're confident — adopted in prod by importing existing
> resources into state.

## Layout

```
infra/
  bootstrap/        # One-time, local state, run by a human.
                    # Creates GCP projects, Spacelift SAs + IAM,
                    # and the Spacelift stacks themselves.
  modules/
    gyrinx/         # The application module: Cloud Run, Cloud SQL,
                    # GCS uploads, CDN, Secret Manager shells, IAM.
                    # Consumed by env wrappers.
  environments/
    staging/        # Wrapper for gyrinx-staging.
    prod/           # Wrapper for windy-ellipse-440618-p9 (existing prod).
```

Each env wrapper is a thin module call. **No backend.tf** — state is
managed by Spacelift.

## Mental model

- **bootstrap** is "who can change what, and which Spacelift stacks
  exist." Runs once by hand with local state.
- **modules/gyrinx** is the shape of the application.
- **environments/{staging,prod}** are thin wrappers that set the per-env
  knobs.
- Day-to-day TF runs in **Spacelift**, triggered by pushes to `main`
  that touch the env's `project_root` (or shared `modules/**`).

## Workflow (staging end-to-end)

See `bootstrap/README.md` for the detailed operator steps. Short
version:

1. Manual prerequisites (Spacelift signup, GitHub App install, API key).
2. `cd infra/bootstrap && terraform init && terraform apply -target=...`
   to create the GCP project + Spacelift SA.
3. `scripts/setup-keys.sh staging` to mint and stash the SA JSON key.
4. `terraform apply` to upload the key and create the Spacelift stack.
5. Trigger the first run in the Spacelift UI; confirm the plan; let it apply.
