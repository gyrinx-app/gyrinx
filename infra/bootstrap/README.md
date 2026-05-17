# bootstrap

One-time setup, run by a human, **local state**.

Creates the GCP projects, the per-env Spacelift service accounts (and
project-scoped IAM bindings for them), and the Spacelift stacks that
will manage everything else. After this is applied once, all
day-to-day Terraform happens via Spacelift — there is no other
"human-run" TF root.

## What it creates

- One `google_project` per env (where `create_project = true`).
- One `spacelift` service account per env, project-scoped, with the
  broad roles needed to manage Cloud Run / Cloud SQL / GCS / Pub/Sub
  / Secret Manager / IAM inside its own project.
- One `spacelift_stack` per env (`gyrinx-staging`, `gyrinx-prod`)
  pointing at `infra/environments/<env>/` in this repo. State is
  managed by Spacelift (`manage_state = true`); the env wrappers have
  no backend.tf.
- A `spacelift_mounted_file` on each stack containing the GCP SA JSON
  key, and a `GOOGLE_APPLICATION_CREDENTIALS` env var pointing at it
  (`/mnt/workspace/gcp-credentials.json`).

## What it does NOT do

- **Does not create SA keys.** Keys are minted out-of-band via
  `scripts/setup-keys.sh`, stored at
  `~/.config/gyrinx/spacelift-keys/spacelift-<env>.json`, and
  symlinked into `infra/bootstrap/keys/`. Terraform reads them via
  `filebase64()` — the key value never enters TF state.
- **Does not configure the Spacelift account itself.** You need a
  Spacelift account + GitHub VCS integration + an admin API key
  *before* you can apply this. See "Prerequisites" below.
- **Does not configure WIF / OIDC.** Free tier uses long-lived JSON
  keys — `gyrinx.spacelift.io` doesn't have OIDC available.

## Prerequisites (manual)

1. Sign up at <https://spacelift.io/>, free plan.
2. Connect your GitHub via the Spacelift GitHub App; install on the
   `gyrinx-app/gyrinx` repo.
3. Settings → API keys → create an admin API key. Save the config file
   somewhere safe (`~/Downloads/api-key-gyrinx-spacelift-*.config`).
4. Note your Spacelift account URL (e.g. `https://gyrinx.app.spacelift.io`).

## Operator workflow

```bash
cd infra/bootstrap

# Spacelift creds (from the config file you saved above)
export SPACELIFT_API_KEY_ENDPOINT="https://<your-org>.app.spacelift.io"
export SPACELIFT_API_KEY_ID="01KRVR6TP31F6BZKP6717HW7YM"
export SPACELIFT_API_KEY_SECRET="<secret from the .config file>"

# GCP creds — your own gcloud / ADC. Must have rights to:
#   - Create projects + link billing (for envs with create_project = true)
#   - Create SAs and grant project IAM in the target project(s)
gcloud auth application-default login

# 1st pass: create projects, SAs, IAM. Stacks need the mounted-file
#           keys to exist, so target the GCP-side resources first.
terraform init
terraform apply \
  -target=google_project.this \
  -target=google_project_service.base \
  -target=google_service_account.spacelift \
  -target=google_project_iam_member.spacelift

# Mint the SA keys (one file per env in ~/.config/gyrinx/spacelift-keys/)
scripts/setup-keys.sh staging
# scripts/setup-keys.sh prod    # only when ready

# 2nd pass: full apply — uploads keys to Spacelift stacks.
terraform apply
```

The two-pass thing exists because `spacelift_mounted_file` reads the
JSON via `filebase64()` at *plan* time, which fails if the file
doesn't exist yet. The first targeted apply makes the SA so we have
something to mint a key for; the second apply does everything else.
A second apply after `setup-keys.sh` is idempotent.

## Rotating a key

```bash
rm ~/.config/gyrinx/spacelift-keys/spacelift-staging.json
scripts/setup-keys.sh staging
terraform apply              # uploads the new key to Spacelift
gcloud iam service-accounts keys list \
  --iam-account=spacelift@gyrinx-staging.iam.gserviceaccount.com \
  --project=gyrinx-staging
# delete the old key in the GCP console once the new one is confirmed working
```

## State

Local. `terraform.tfstate` lives next to this README and is gitignored.
Back it up to 1Password (or similar) — losing it doesn't lose the cloud
resources, but you'd need to `terraform import` everything to get it
back under management.
