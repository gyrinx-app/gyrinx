# One `spacelift` service account per environment, inside that env's project.
# Spacelift authenticates as this SA via a long-lived JSON key (free tier =
# no OIDC). Roles are project-scoped — Spacelift only ever has rights inside
# the project it's managing.

resource "google_service_account" "spacelift" {
  for_each = var.environments

  project      = each.value.project_id
  account_id   = "spacelift"
  display_name = "Spacelift (${each.key})"
  description  = "Used by Spacelift to manage ${each.key} infrastructure via a long-lived key."

  depends_on = [google_project_service.base]
}

# Roles the Spacelift SA needs inside each environment's project to do
# everything the main app module (Cloud Run, Cloud SQL, GCS, Pub/Sub,
# Secret Manager, IAM bindings, CDN) requires.
locals {
  spacelift_roles = toset([
    "roles/artifactregistry.admin",
    "roles/cloudscheduler.admin",
    "roles/cloudsql.admin",
    "roles/compute.networkAdmin",
    "roles/compute.securityAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/pubsub.admin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/run.admin",
    "roles/secretmanager.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
  ])
}

resource "google_project_iam_member" "spacelift" {
  for_each = {
    for pair in flatten([
      for env, cfg in var.environments : [
        for role in local.spacelift_roles : {
          key     = "${env}:${role}"
          env     = env
          project = cfg.project_id
          role    = role
        }
      ]
    ]) : pair.key => pair
  }

  project = each.value.project
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.spacelift[each.value.env].email}"
}
