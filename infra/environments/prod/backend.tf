terraform {
  backend "gcs" {
    bucket = "gyrinx-prod-tfstate"
    prefix = "gyrinx"
  }
}
