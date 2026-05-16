# Optional project creation. Set `create_project = true` in tfvars to bring
# up a new GCP project (typically for a fresh staging env). For prod or any
# pre-existing project, leave it false — the project is treated as a given.
#
# When creating: billing_account_id is required; org_id / folder_id are
# optional (omit both for a no-parent / personal project).

resource "google_project" "this" {
  count = var.create_project ? 1 : 0

  name            = coalesce(var.project_name, var.project_id)
  project_id      = var.project_id
  billing_account = var.billing_account_id
  org_id          = var.org_id
  folder_id       = var.folder_id

  auto_create_network = var.auto_create_network

  labels = merge(var.labels, {
    environment = var.environment
  })

  lifecycle {
    precondition {
      condition     = !(var.org_id != null && var.folder_id != null)
      error_message = "Set at most one of org_id or folder_id."
    }
    precondition {
      condition     = var.project_name != null
      error_message = "project_name must be set when create_project = true."
    }
  }
}

# A handle the rest of the module uses regardless of whether we created the
# project or it was pre-existing. Forces an edge in the dependency graph so
# APIs / state bucket / IAM all wait for project creation to land.
locals {
  project_id = var.create_project ? google_project.this[0].project_id : var.project_id
}
