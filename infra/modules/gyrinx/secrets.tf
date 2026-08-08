# Secret Manager *shells*. Values are populated out of band:
#
#   echo -n "<value>" | gcloud secrets versions add <secret-id> --data-file=-
#
# The Cloud Run runtime SA is granted accessor on each.

resource "google_secret_manager_secret" "shells" {
  for_each = var.secrets

  project   = var.project_id
  secret_id = each.value

  replication {
    auto {}
  }

  labels = local.labels
}

resource "google_secret_manager_secret_iam_member" "runtime_accessor" {
  for_each = var.secrets

  project   = google_secret_manager_secret.shells[each.value].project
  secret_id = google_secret_manager_secret.shells[each.value].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}
