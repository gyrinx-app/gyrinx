# gyrinx module

The application stack: Cloud Run service, Cloud SQL Postgres, uploads bucket
(+ CDN), Secret Manager shells, and IAM. One module, multiple env wrappers.

## What's in here

| File                | Resources                                             |
|---------------------|-------------------------------------------------------|
| `iam.tf`            | Cloud Run runtime SA, pubsub-invoker SA, bindings.    |
| `cloud_run.tf`      | The Cloud Run service (placeholder image).            |
| `cloud_sql.tf`      | Cloud SQL Postgres instance + database + app user.    |
| `pubsub.tf`         | (Empty — topics/subscriptions are app-provisioned.)   |
| `gcs.tf`            | Uploads bucket, with optional CDN backend bucket.     |
| `cdn.tf`            | Load balancer for `cdn.<env-domain>` (optional).      |
| `secrets.tf`        | Secret Manager **shells** (values out of band).       |
| `outputs.tf`        | Service URL, DB connection name, bucket name, etc.    |

## What's NOT in here

- **Pub/Sub topics and subscriptions.** Auto-provisioned by the app at
  startup (`gyrinx/tasks/provisioning.py`). The module creates the
  `pubsub-invoker` service account it needs, and grants Cloud Run
  invoker on the service. Topics arrive when the app boots.
- **Cloud Scheduler jobs.** Same — app-provisioned.
- **Secret values.** We create the secret shells; values are populated
  out of band via `gcloud secrets versions add`.
- **Cloud Run image tag / env var values / scale knobs that drift on every
  deploy.** Cloud Build deploys handle `--image=...` and `--set-env-vars`.
  We set a placeholder and use `lifecycle.ignore_changes` to stop fighting
  the CI pipeline.
- **Domain mapping.** TODO — prod has `gyrinx.app` mapped to Cloud Run
  natively (`google_cloud_run_domain_mapping`). Not Terraformed yet;
  add when we adopt prod.
- **DNS.** The DNS zone for gyrinx.app lives at the registrar and is not
  GCP-managed (yet).

## Variables of note

- `environment` — drives naming and "is this the prod project" toggles.
- `enable_cdn` — whether to build the public load balancer for
  `cdn.<base_domain>`. In staging, default off; flip on to test.
- `db_tier`, `db_disk_size_gb`, `db_deletion_protection` — sized down in
  staging (see `environments/staging/main.tf`).

See `variables.tf` for the full list.
