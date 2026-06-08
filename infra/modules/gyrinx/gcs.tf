resource "google_storage_bucket" "uploads" {
  project       = var.project_id
  name          = local.uploads_bucket_name
  location      = var.region
  force_destroy = var.uploads_bucket_force_destroy

  uniform_bucket_level_access = true

  # The bucket itself is private; the CDN backend bucket (if enabled) makes
  # objects public via the load balancer. Direct GCS reads still need IAM.
  public_access_prevention = var.enable_cdn ? "inherited" : "enforced"

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type", "Cache-Control"]
    max_age_seconds = 3600
  }

  versioning {
    enabled = false
  }

  labels = local.labels
}

# The Cloud Run runtime SA reads + writes user uploads.
resource "google_storage_bucket_iam_member" "uploads_runtime" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

# If the CDN is on, allUsers need to read objects via the LB. We grant
# objectViewer on the bucket — public_access_prevention is "inherited"
# above, so this works.
resource "google_storage_bucket_iam_member" "uploads_public_read" {
  count = var.enable_cdn ? 1 : 0

  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}
