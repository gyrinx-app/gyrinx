resource "google_cloud_run_v2_service" "app" {
  project  = var.project_id
  name     = var.service_name
  location = var.region

  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.environment == "prod"

  labels = local.labels

  template {
    service_account = google_service_account.cloud_run_runtime.email

    scaling {
      min_instance_count = var.cloud_run_min_instances
      max_instance_count = var.cloud_run_max_instances
    }

    timeout                          = "${var.cloud_run_timeout_seconds}s"
    max_instance_request_concurrency = var.cloud_run_concurrency

    containers {
      image = var.cloud_run_placeholder_image

      resources {
        limits = {
          cpu    = var.cloud_run_cpu
          memory = var.cloud_run_memory
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      # Cloud SQL is reached via the Cloud SQL Auth Proxy sidecar, set up
      # via the volumes block below. Actual DB host / connection name is
      # injected into the app at deploy time via env vars (managed by CI,
      # not TF).
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GS_BUCKET_NAME"
        value = google_storage_bucket.uploads.name
      }
      env {
        name  = "TASKS_ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "TASKS_SERVICE_ACCOUNT"
        value = google_service_account.pubsub_invoker.email
      }
      env {
        name  = "SCHEDULER_LOCATION"
        value = var.region
      }
      env {
        name  = "DJANGO_SETTINGS_MODULE"
        value = "gyrinx.settings_prod"
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
  }

  # Hand back to CI for image rolls, env var values, scale knobs.
  # Terraform owns service shape; CI owns runtime config.
  lifecycle {
    ignore_changes = [
      client,
      client_version,
      template[0].containers[0].image,
      template[0].annotations,
    ]
  }
}

# Public access. Default is on; flip via var if the env should be locked down.
resource "google_cloud_run_v2_service_iam_member" "public" {
  count = var.cloud_run_allow_unauthenticated ? 1 : 0

  project  = google_cloud_run_v2_service.app.project
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Pub/Sub push subscriptions, created by the app at startup, need to invoke
# the service. Bind at the service level rather than project-wide.
resource "google_cloud_run_v2_service_iam_member" "pubsub_invoker" {
  project  = google_cloud_run_v2_service.app.project
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}

# The pubsub-invoker SA needs to mint OIDC tokens for itself when used as a
# push auth identity. Granting tokenCreator on the SA to its own email is
# the standard pattern.
resource "google_service_account_iam_member" "pubsub_invoker_token_creator" {
  service_account_id = google_service_account.pubsub_invoker.id
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}
