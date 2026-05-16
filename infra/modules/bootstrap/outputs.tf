output "project_id" {
  description = "Project this bootstrap targeted (created here if create_project = true)."
  value       = local.project_id
}

output "project_number" {
  description = "Project number (only known when create_project = true)."
  value       = var.create_project ? google_project.this[0].number : null
}

output "state_bucket" {
  description = "GCS bucket holding the main module's Terraform state."
  value       = google_storage_bucket.tf_state.name
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository for Cloud Run images."
  value       = google_artifact_registry_repository.images.repository_id
}

output "artifact_registry_url" {
  description = "Full Docker URL prefix, e.g. europe-west2-docker.pkg.dev/<project>/<repo>."
  value       = "${google_artifact_registry_repository.images.location}-docker.pkg.dev/${local.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "terraform_deploy_sa_email" {
  description = "Email of the terraform deploy service account."
  value       = google_service_account.terraform_deploy.email
}
