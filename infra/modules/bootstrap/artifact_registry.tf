# Docker repo for Cloud Run images. Mirrors the path the existing
# Cloud Build pipeline already uses:
#   europe-west2-docker.pkg.dev/<project>/cloud-run-source-deploy/<repo>/<service>
resource "google_artifact_registry_repository" "images" {
  project       = local.project_id
  location      = var.region
  repository_id = var.artifact_registry_repo_id
  description   = "Docker images for Cloud Run deployments"
  format        = "DOCKER"

  labels = var.labels

  depends_on = [google_project_service.apis]
}
