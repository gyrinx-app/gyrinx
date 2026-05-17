terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.20"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.20"
    }
    spacelift = {
      source  = "spacelift-io/spacelift"
      version = "~> 1.0"
    }
  }

  # Local state on purpose. This is the one module a human runs by hand,
  # and it's small enough that the state file fits comfortably in
  # ~/.config/gyrinx/.
}
