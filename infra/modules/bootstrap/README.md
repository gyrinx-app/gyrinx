# bootstrap module

One-time setup, run by a human, with **local state**.

## What it creates

- *(optional)* The GCP project itself (`create_project = true`). Billing
  is linked at create time via `billing_account_id`. Off by default so
  bootstrap can also be pointed at a pre-existing project (prod).
- The GCS bucket used as the Terraform state backend for the main `gyrinx`
  module (one bucket per environment, versioning + lifecycle on noncurrent
  versions).
- Project services (API enablement) — every API the main module touches.
- An Artifact Registry repository for Cloud Run images.
- The Terraform deploy service account (`terraform-deploy@<project>.iam.gserviceaccount.com`)
  with the project-level roles it needs to manage the rest of the stack. This
  SA is what a future CI run would impersonate.

## What it does NOT do

- No workload-identity-federation pool/provider yet. We'll add that when we
  wire this up to a CI system. For now the bootstrap is run by a human who
  already has Owner on the project (or rights to create one).
- No org-level policies — we don't own an org.
- Nothing application-specific (DB, buckets, Cloud Run). That all lives in
  `../gyrinx`.

## Running

State is local; this is intentional. Run from this directory.

For a fresh **staging** project (creates the project, links billing, then
sets up state bucket / APIs / AR / SAs):

```bash
gcloud billing accounts list   # grab your billing account ID
# Edit ../../environments/staging/bootstrap.tfvars and fill in billing_account_id.

terraform init
terraform apply -var-file=../../environments/staging/bootstrap.tfvars
```

For **prod** (project already exists; bootstrap manages everything *inside*
it):

```bash
terraform init
terraform apply -var-file=../../environments/prod/bootstrap.tfvars
```

Keep the `terraform.tfstate` for each env somewhere safe (a 1Password vault,
not git). The blast radius of losing it is "the bootstrap SA + state bucket
exist but TF can't manage them" — you can re-import.
