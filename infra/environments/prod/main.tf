locals {
  project_id = "windy-ellipse-440618-p9"
  region     = "europe-west2"
}

provider "google" {
  project = local.project_id
  region  = local.region
}

provider "google-beta" {
  project = local.project_id
  region  = local.region
}

module "gyrinx" {
  source = "../../modules/gyrinx"

  project_id  = local.project_id
  region      = local.region
  environment = "prod"

  # Match the names already in prod so an eventual `terraform import` lands
  # cleanly. Existing resources are `gyrinx-app-bootstrap-*`.
  name_prefix         = "gyrinx-app-bootstrap"
  uploads_bucket_name = "gyrinx-app-bootstrap-uploads"
  db_instance_name    = "gyrinx-app-bootstrap-db"

  # Cloud SQL — sized to whatever prod is actually running. These are
  # placeholders pending an import; adjust before apply.
  db_tier                   = "db-custom-1-3840"
  db_disk_size_gb           = 20
  db_deletion_protection    = true
  db_backups_enabled        = true
  db_backup_retention_count = 7

  # Cloud Run
  cloud_run_min_instances = 0
  cloud_run_max_instances = 10
  cloud_run_cpu           = "2"
  cloud_run_memory        = "2Gi"

  uploads_bucket_force_destroy = false

  enable_cdn = true
  cdn_domain = "cdn.gyrinx.app"

  # Existing prod secret IDs (note the typo `boostrap` on the Discord one).
  secrets = [
    "gyrinx-app-bootstrap-django-secret-key",
    "gyrinx-app-bootstrap-db-config",
    "gyrinx-app-bootstrap-email-host-password",
    "gyrinx-app-bootstrap-patreon-hook-secret",
    "gyrinx-app-bootstrap-discord-public-key",
    "gyrinx-app-bootstrap-discord-application-id",
    "gyrinx-app-bootstrap-discord-bot-token",
    "gyrinx-app-bootstrap-github-dispatch-token",
    "gyrinx-app-bootstrap-recaptcha-private-key",
    "gyrinx-app-boostrap-discord-webhook-url", # NB: typo matches prod
  ]
}

output "cloud_run_url" {
  value = module.gyrinx.cloud_run_url
}

output "db_connection_name" {
  value = module.gyrinx.db_connection_name
}

output "uploads_bucket" {
  value = module.gyrinx.uploads_bucket
}

output "cdn_ip" {
  value = module.gyrinx.cdn_ip_address
}
