# Optional project creation. Per-env via `create_project`. For environments
# whose project already exists (e.g. prod), set `create_project = false` and
# pass the existing project_id.

resource "google_project" "this" {
  for_each = {
    for env, cfg in var.environments : env => cfg if cfg.create_project
  }

  project_id      = each.value.project_id
  name            = coalesce(each.value.project_name, each.value.project_id)
  billing_account = var.billing_account_id

  org_id              = var.org_id
  auto_create_network = false

  labels = merge(each.value.labels, {
    environment = each.key
    app         = "gyrinx"
    managed-by  = "terraform"
  })
}

# Base APIs every workload project needs. The main app stack enables its
# own additional APIs (cloud run, sql, pubsub, ...) when it runs — keeping
# *this* module minimal.
locals {
  base_apis = toset([
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
  ])
}

resource "google_project_service" "base" {
  for_each = {
    for pair in flatten([
      for env, cfg in var.environments : [
        for api in local.base_apis : {
          key        = "${env}:${api}"
          project_id = cfg.project_id
          api        = api
        }
      ]
    ]) : pair.key => pair
  }

  project = each.value.project_id
  service = each.value.api

  disable_on_destroy         = false
  disable_dependent_services = false

  depends_on = [google_project.this]
}
