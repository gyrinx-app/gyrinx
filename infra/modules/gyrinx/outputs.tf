output "cloud_run_service_name" {
  description = "Name of the Cloud Run service."
  value       = google_cloud_run_v2_service.app.name
}

output "cloud_run_url" {
  description = "Default URL of the Cloud Run service."
  value       = google_cloud_run_v2_service.app.uri
}

output "cloud_run_runtime_sa_email" {
  description = "Cloud Run runtime service account email."
  value       = google_service_account.cloud_run_runtime.email
}

output "pubsub_invoker_sa_email" {
  description = "Service account used by Pub/Sub push subscriptions to invoke Cloud Run."
  value       = google_service_account.pubsub_invoker.email
}

output "db_instance_name" {
  description = "Cloud SQL instance name."
  value       = google_sql_database_instance.main.name
}

output "db_connection_name" {
  description = "Cloud SQL connection name (used by Cloud SQL Auth Proxy)."
  value       = google_sql_database_instance.main.connection_name
}

output "db_public_ip" {
  description = "Public IP of the Cloud SQL instance (when enabled)."
  value       = google_sql_database_instance.main.public_ip_address
}

output "uploads_bucket" {
  description = "GCS bucket holding user uploads."
  value       = google_storage_bucket.uploads.name
}

output "cdn_ip_address" {
  description = "Global IP for the CDN (null when CDN is disabled)."
  value       = length(google_compute_global_address.cdn) > 0 ? google_compute_global_address.cdn[0].address : null
}

output "secret_ids" {
  description = "Secret IDs created in Secret Manager."
  value       = [for s in google_secret_manager_secret.shells : s.secret_id]
}
