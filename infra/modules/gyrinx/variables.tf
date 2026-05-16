variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "Default region for regional resources."
  type        = string
  default     = "europe-west2"
}

variable "environment" {
  description = "Short environment name (staging, prod). Drives naming and protection toggles."
  type        = string
  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be one of: staging, prod."
  }
}

variable "name_prefix" {
  description = <<-EOT
    Prefix used for resource names. Defaults to `gyrinx-<environment>`.
    Existing prod resources were named `gyrinx-app-bootstrap-*`; set this to
    `gyrinx-app-bootstrap` when importing prod so the module's names line up
    with what's already there.
  EOT
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Cloud Run
# ---------------------------------------------------------------------------

variable "service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "gyrinx"
}

variable "cloud_run_min_instances" {
  description = "Minimum Cloud Run instances. 0 = scale to zero."
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Maximum Cloud Run instances."
  type        = number
  default     = 10
}

variable "cloud_run_cpu" {
  description = "CPU request for each Cloud Run instance."
  type        = string
  default     = "1"
}

variable "cloud_run_memory" {
  description = "Memory request for each Cloud Run instance."
  type        = string
  default     = "1Gi"
}

variable "cloud_run_concurrency" {
  description = "Max concurrent requests per Cloud Run instance."
  type        = number
  default     = 80
}

variable "cloud_run_timeout_seconds" {
  description = "Request timeout for Cloud Run."
  type        = number
  default     = 300
}

variable "cloud_run_allow_unauthenticated" {
  description = "Whether allUsers can invoke the Cloud Run service. True for the public website."
  type        = bool
  default     = true
}

variable "cloud_run_placeholder_image" {
  description = "Image used when Terraform first creates the service. Real images come from Cloud Build."
  type        = string
  default     = "gcr.io/cloudrun/hello"
}

# ---------------------------------------------------------------------------
# Cloud SQL
# ---------------------------------------------------------------------------

variable "db_instance_name" {
  description = "Cloud SQL instance name. Defaults to `<name_prefix>-db`."
  type        = string
  default     = null
}

variable "db_version" {
  description = "Postgres version."
  type        = string
  default     = "POSTGRES_16"
}

variable "db_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-f1-micro"
}

variable "db_disk_size_gb" {
  description = "Initial disk size in GB. Auto-resize is enabled."
  type        = number
  default     = 10
}

variable "db_disk_type" {
  description = "Disk type (PD_SSD or PD_HDD)."
  type        = string
  default     = "PD_SSD"
}

variable "db_deletion_protection" {
  description = "Cloud SQL deletion protection. On for prod, off for staging."
  type        = bool
  default     = true
}

variable "db_backups_enabled" {
  description = "Whether automated backups are enabled."
  type        = bool
  default     = true
}

variable "db_backup_retention_count" {
  description = "Number of automated backups to retain."
  type        = number
  default     = 7
}

variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "gyrinx"
}

variable "db_app_user" {
  description = "Application database user."
  type        = string
  default     = "gyrinx"
}

# ---------------------------------------------------------------------------
# Uploads bucket + CDN
# ---------------------------------------------------------------------------

variable "uploads_bucket_name" {
  description = "GCS bucket for user uploads. Must be globally unique. Defaults to `<name_prefix>-uploads`."
  type        = string
  default     = null
}

variable "uploads_bucket_force_destroy" {
  description = "Whether the uploads bucket can be deleted while non-empty. True in staging only."
  type        = bool
  default     = false
}

variable "enable_cdn" {
  description = "Provision a global HTTPS load balancer in front of the uploads bucket."
  type        = bool
  default     = false
}

variable "cdn_domain" {
  description = "Domain name for the CDN (e.g. cdn.gyrinx.app). Required when enable_cdn=true."
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Secret Manager
# ---------------------------------------------------------------------------

variable "secrets" {
  description = <<-EOT
    Map of Secret Manager secret IDs to create as empty shells. Values are
    populated out of band. The Cloud Run runtime SA is granted accessor on each.
  EOT
  type        = set(string)
  default = [
    "django-secret-key",
    "db-config",
    "email-host-password",
    "patreon-hook-secret",
    "discord-public-key",
    "discord-application-id",
    "discord-bot-token",
    "github-dispatch-token",
    "recaptcha-private-key",
    "discord-webhook-url",
  ]
}

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

variable "labels" {
  description = "Labels applied to taggable resources."
  type        = map(string)
  default     = {}
}

locals {
  name_prefix = coalesce(var.name_prefix, "gyrinx-${var.environment}")

  uploads_bucket_name = coalesce(
    var.uploads_bucket_name,
    "${local.name_prefix}-uploads",
  )

  db_instance_name = coalesce(
    var.db_instance_name,
    "${local.name_prefix}-db",
  )

  default_labels = {
    managed-by  = "terraform"
    environment = var.environment
    app         = "gyrinx"
  }

  labels = merge(local.default_labels, var.labels)
}
