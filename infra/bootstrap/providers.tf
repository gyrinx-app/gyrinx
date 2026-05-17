# Spacelift provider. Endpoint comes from terraform.tfvars (it's just a URL);
# the API key id + secret come from a gitignored secrets.auto.tfvars
# auto-loaded by Terraform (see secrets.auto.tfvars.example).
provider "spacelift" {
  api_key_endpoint = var.spacelift_api_endpoint
  api_key_id       = var.spacelift_api_key_id
  api_key_secret   = var.spacelift_api_key_secret
}

# Default google provider — falls back to user ADC. Most resources override
# `project` explicitly, so this is just a safety net.
provider "google" {
  region = var.region
}

provider "google-beta" {
  region = var.region
}
