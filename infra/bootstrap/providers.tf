# Spacelift provider. Authenticate via env vars set on the operator's shell:
#
#   export SPACELIFT_API_KEY_ENDPOINT="https://<your-org>.app.spacelift.io"
#   export SPACELIFT_API_KEY_ID="01KRVR6TP31F6BZKP6717HW7YM"
#   export SPACELIFT_API_KEY_SECRET="..."   # from ~/Downloads/api-key-*.config
#
# (Do not put these in this file or in tfvars.)
provider "spacelift" {}

# Default google provider — falls back to user ADC. Most resources override
# `project` explicitly, so this is just a safety net.
provider "google" {
  region = var.region
}

provider "google-beta" {
  region = var.region
}
