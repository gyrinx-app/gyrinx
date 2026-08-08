# One stack per environment, each pointing at infra/environments/<env>/
# in the gyrinx repo. State managed by Spacelift. Auto-deploy is opt-in
# per env (off by default; flip on for staging once it's boring).

resource "spacelift_stack" "env" {
  for_each = var.environments

  name        = "gyrinx-${each.key}"
  description = "gyrinx ${each.key} environment"

  repository = var.github_repo
  branch     = var.stack_branch

  github_enterprise {
    namespace = var.github_namespace
  }

  project_root             = "infra/environments/${each.key}"
  additional_project_globs = ["infra/modules/**"]

  # Terraform (not OpenTofu) — match what we develop with locally.
  terraform_version  = var.terraform_version
  manage_state       = true
  autodeploy         = each.value.autodeploy

  terraform_smart_sanitization     = true
  enable_well_known_secret_masking = true
  protect_from_deletion            = true

  labels = ["env:${each.key}", "app:gyrinx"]
}

# Mount the GCP credential JSON for this env on the corresponding stack.
# The file is read at plan time via filebase64() — it must exist on disk
# (see scripts/setup-keys.sh). Keeping the JSON out of TF state means
# rotating the key doesn't churn state, and `terraform.tfstate` doesn't
# carry credential material.
resource "spacelift_mounted_file" "gcp_credentials" {
  for_each = var.environments

  stack_id      = spacelift_stack.env[each.key].id
  relative_path = "gcp-credentials.json"
  content       = filebase64("${path.module}/${var.keys_dir}/spacelift-${each.key}.json")
  write_only    = true
  description   = "GCP service account key for ${google_service_account.spacelift[each.key].email}"
}

resource "spacelift_environment_variable" "google_application_credentials" {
  for_each = var.environments

  stack_id    = spacelift_stack.env[each.key].id
  name        = "GOOGLE_APPLICATION_CREDENTIALS"
  value       = "/mnt/workspace/gcp-credentials.json"
  write_only  = false
  description = "Path to the mounted GCP service account key"
}

# Expose the project ID to the stack as TF_VAR_project_id so env wrappers
# can keep their main.tf provider-agnostic. (Currently we hardcode project
# IDs in environments/*/main.tf, so this is belt-and-braces.)
resource "spacelift_environment_variable" "project_id" {
  for_each = var.environments

  stack_id    = spacelift_stack.env[each.key].id
  name        = "TF_VAR_project_id"
  value       = each.value.project_id
  write_only  = false
  description = "GCP project ID for this environment"
}
