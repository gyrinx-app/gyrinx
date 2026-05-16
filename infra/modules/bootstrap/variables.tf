variable "project_id" {
  description = "GCP project ID this bootstrap targets."
  type        = string
}

variable "region" {
  description = "Default region for regional resources (Artifact Registry, etc.)."
  type        = string
  default     = "europe-west2"
}

variable "environment" {
  description = "Short environment name (staging, prod). Used to scope bucket / SA names."
  type        = string
  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be one of: staging, prod."
  }
}

variable "state_bucket_name" {
  description = "Name of the GCS bucket that will hold the main module's Terraform state. Must be globally unique."
  type        = string
}

variable "artifact_registry_repo_id" {
  description = "Artifact Registry repo ID for Cloud Run images."
  type        = string
  default     = "cloud-run-source-deploy"
}

variable "labels" {
  description = "Labels applied to taggable resources created here."
  type        = map(string)
  default = {
    managed-by = "terraform"
    component  = "bootstrap"
  }
}

# ---------------------------------------------------------------------------
# Optional: create the GCP project from Terraform
# ---------------------------------------------------------------------------
#
# Off by default — for projects that already exist (prod), Terraform should
# not be the one creating them. For a fresh environment (staging), flip this
# on and supply `billing_account_id` so the project is wired up end-to-end.

variable "create_project" {
  description = "If true, create the GCP project as part of bootstrap. If false, the project must already exist."
  type        = bool
  default     = false
}

variable "project_name" {
  description = "Human-readable project name. Required when create_project = true."
  type        = string
  default     = null
}

variable "billing_account_id" {
  description = "Billing account ID to link to the new project (e.g. 0X0X0X-0X0X0X-0X0X0X). Required when create_project = true."
  type        = string
  default     = null
}

variable "org_id" {
  description = "Organization ID to create the project under. Leave null for no-parent (personal) projects."
  type        = string
  default     = null
}

variable "folder_id" {
  description = "Folder ID to create the project under. Mutually exclusive with org_id."
  type        = string
  default     = null
}

variable "auto_create_network" {
  description = "Whether the default VPC network is auto-created on project creation. We don't need it; default off."
  type        = bool
  default     = false
}
