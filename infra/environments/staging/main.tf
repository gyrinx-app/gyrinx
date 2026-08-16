locals {
  project_id = "gyrinx-staging"
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
  environment = "staging"

  # Cheap Cloud SQL — staging is disposable.
  db_tier                   = "db-f1-micro"
  db_disk_size_gb           = 10
  db_deletion_protection    = false
  db_backups_enabled        = false
  db_backup_retention_count = 1

  # Cloud Run: keep scale low.
  cloud_run_min_instances = 0
  cloud_run_max_instances = 2
  cloud_run_cpu           = "1"
  cloud_run_memory        = "512Mi"

  # Uploads bucket: allow nuking on teardown.
  uploads_bucket_force_destroy = true

  # CDN off in staging — we don't have a DNS record to point at it.
  enable_cdn = false
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

output "runtime_sa" {
  value = module.gyrinx.cloud_run_runtime_sa_email
}
