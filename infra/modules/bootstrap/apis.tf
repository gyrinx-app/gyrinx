# Enable every GCP API the main module touches. This is the gating
# resource — everything in the main module should `depends_on` the
# right subset of these.
#
# Bootstrap enables the full set because the alternative — enabling
# per-module — creates a chicken-and-egg with the state bucket itself.

locals {
  services = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudkms.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtrace.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ])
}

resource "google_project_service" "apis" {
  for_each = local.services
  project  = local.project_id
  service  = each.value

  # Keep services enabled even if this module is destroyed — disabling
  # an API drops every resource using it.
  disable_on_destroy         = false
  disable_dependent_services = false
}
