# ---------------------------------------------------------------------------
# What this module needs to know
# ---------------------------------------------------------------------------

variable "region" {
  description = "Default GCP region."
  type        = string
  default     = "europe-west2"
}

variable "billing_account_id" {
  description = "GCP billing account ID (XXXXXX-XXXXXX-XXXXXX) to link new projects to."
  type        = string
}

variable "org_id" {
  description = <<-EOT
    GCP organisation ID under which to create new projects. The existing
    prod project is in org 533848338530 (gyrinx.app); putting new ones
    in the same org keeps the management hierarchy consistent.
    Set to null to create no-parent (personal) projects.
  EOT
  type    = string
  default = null
}

variable "environments" {
  description = <<-EOT
    Map of environment name => config. Each entry produces:
      - (optional) a GCP project, if `create_project = true`
      - a `spacelift` service account inside that project
      - IAM bindings for that SA
      - a Spacelift stack pointing at infra/environments/<env>/
      - a mounted GCP credentials file on the stack

    Long-lived SA keys are NOT created by Terraform. The operator
    generates them out-of-band (see scripts/setup-keys.sh) and places
    them at <key_path>; Terraform reads the JSON via filebase64() to
    populate the Spacelift mounted file. This keeps the key value out
    of TF state.
  EOT
  type = map(object({
    project_id     = string
    create_project = bool
    project_name   = optional(string)
    autodeploy     = optional(bool, false)
    labels         = optional(map(string), {})
  }))
}

variable "github_namespace" {
  description = "GitHub org/user that owns the repo."
  type        = string
  default     = "gyrinx-app"
}

variable "github_repo" {
  description = "GitHub repository name (without the org)."
  type        = string
  default     = "gyrinx"
}

variable "stack_branch" {
  description = "Git branch each Spacelift stack tracks."
  type        = string
  default     = "main"
}

variable "terraform_version" {
  description = "Terraform version Spacelift should run."
  type        = string
  default     = "1.14.6"
}

variable "keys_dir" {
  description = <<-EOT
    Path (relative to this module) to a directory containing one JSON key
    per environment, named `spacelift-<env>.json`. Typically a symlink
    to ~/.config/gyrinx/spacelift-keys/. Files are read with
    filebase64() and never committed.
  EOT
  type    = string
  default = "keys"
}
