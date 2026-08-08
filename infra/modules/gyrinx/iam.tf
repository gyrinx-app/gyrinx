# Runtime service account for the Cloud Run service. One SA per service —
# scoped to what gyrinx itself actually needs.
resource "google_service_account" "cloud_run_runtime" {
  project      = var.project_id
  account_id   = "${local.name_prefix}-run"
  display_name = "Cloud Run runtime SA for ${var.service_name} (${var.environment})"
}

# Service account Pub/Sub uses when invoking the push endpoint on Cloud Run.
# The app's auto-provisioning code expects this SA at:
#   pubsub-invoker@<project>.iam.gserviceaccount.com
# (see gyrinx/tasks/provisioning.py)
resource "google_service_account" "pubsub_invoker" {
  project      = var.project_id
  account_id   = "pubsub-invoker"
  display_name = "Pub/Sub push invoker for Cloud Run tasks"
}

# What the runtime SA needs at the project level. Keep this list short.
# Anything resource-scoped goes next to that resource.
locals {
  runtime_project_roles = toset([
    "roles/cloudsql.client",          # connect via Cloud SQL Auth Proxy / connector
    "roles/cloudsql.instanceUser",    # IAM DB auth (if/when we move to it)
    "roles/cloudtrace.agent",         # write traces
    "roles/logging.logWriter",        # structured logs to stdout still need writer
    "roles/monitoring.metricWriter",
    # The app itself manages Pub/Sub topics/subs and Scheduler jobs at startup.
    # Grant project-level admin so provisioning.py can create resources idempotently.
    "roles/pubsub.editor",
    "roles/cloudscheduler.admin",
  ])
}

resource "google_project_iam_member" "runtime" {
  for_each = local.runtime_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

# pubsub-invoker just needs to invoke the Cloud Run service. Bound at the
# service level in cloud_run.tf, not project-wide.
