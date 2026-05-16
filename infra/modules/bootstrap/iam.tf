# Terraform deploy service account. The main module's CI run impersonates
# this; for now humans use their own creds and this SA exists for future
# Workload Identity Federation wiring.
resource "google_service_account" "terraform_deploy" {
  project      = local.project_id
  account_id   = "terraform-deploy"
  display_name = "Terraform deploy (managed by bootstrap)"
  description  = "Identity used by Terraform to manage the gyrinx stack."

  depends_on = [google_project_service.apis]
}

# Project-level roles the terraform_deploy SA needs to manage the rest
# of the stack. Scoped to project, not org. Pruned to the resources the
# main module actually creates.
locals {
  terraform_deploy_roles = toset([
    "roles/artifactregistry.admin",
    "roles/cloudscheduler.admin",
    "roles/cloudsql.admin",
    "roles/compute.networkAdmin",         # CDN load balancer pieces
    "roles/compute.securityAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",       # ability to attach SAs to resources
    "roles/pubsub.admin",
    "roles/run.admin",
    "roles/secretmanager.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
  ])
}

resource "google_project_iam_member" "terraform_deploy" {
  for_each = local.terraform_deploy_roles

  project = local.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.terraform_deploy.email}"
}
