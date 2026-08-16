resource "google_sql_database_instance" "main" {
  project          = var.project_id
  name             = local.db_instance_name
  region           = var.region
  database_version = var.db_version

  deletion_protection = var.db_deletion_protection

  settings {
    tier              = var.db_tier
    edition           = "ENTERPRISE"
    availability_type = var.db_availability_type
    disk_type         = var.db_disk_type
    disk_size         = var.db_disk_size_gb
    disk_autoresize   = true

    backup_configuration {
      enabled                        = var.db_backups_enabled
      point_in_time_recovery_enabled = var.db_point_in_time_recovery_enabled
      start_time                     = "03:00"
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = var.db_backup_retention_count
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled = true
      # Public IP, gated by Cloud SQL Auth Proxy + IAM. Matches the
      # current prod setup; private IP would need a VPC peering we
      # don't have yet.
      ssl_mode = "ENCRYPTED_ONLY"
    }

    dynamic "database_flags" {
      for_each = var.db_iam_authentication ? [1] : []
      content {
        name  = "cloudsql.iam_authentication"
        value = "on"
      }
    }

    insights_config {
      query_insights_enabled  = var.db_query_insights_enabled
      record_application_tags = var.db_query_insights_enabled
      record_client_address   = false
    }

    user_labels = local.labels

    # If something else (Cloud Build, an operator) flips maintenance window
    # in the console, don't fight it from Terraform.
    maintenance_window {
      day          = 7 # Sunday
      hour         = 4
      update_track = "stable"
    }
  }
}

resource "google_sql_database" "app" {
  project  = var.project_id
  name     = var.db_name
  instance = google_sql_database_instance.main.name
}

# Generated password for the built-in app user. Real value never leaves
# Terraform state, but Cloud Run reads it from Secret Manager (we copy it
# there via secrets.tf), so app config doesn't need to consult TF.
resource "random_password" "app_db" {
  length  = 32
  special = false
}

resource "google_sql_user" "app" {
  project  = var.project_id
  name     = var.db_app_user
  instance = google_sql_database_instance.main.name
  password = random_password.app_db.result

  # Don't tear down the user on password rotation — handle that manually.
  lifecycle {
    ignore_changes = [password]
  }
}

# Bind the runtime SA as a Cloud SQL IAM DB user too. Only when IAM
# authentication is enabled — without the database flag, this user is
# meaningless and an import against prod would create false diff.
resource "google_sql_user" "runtime_iam" {
  count = var.db_iam_authentication ? 1 : 0

  project  = var.project_id
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
  # Cloud SQL expects the SA email *without* the .gserviceaccount.com suffix
  # for IAM service-account users.
  name = trimsuffix(google_service_account.cloud_run_runtime.email, ".gserviceaccount.com")
}
