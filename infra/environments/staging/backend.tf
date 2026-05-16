# State backend for staging. The bucket is created by the bootstrap module
# (see ./bootstrap.tfvars). When initialising for the first time:
#
#   terraform init -backend-config=backend.hcl
#
# where backend.hcl has the right bucket name. Or use `-reconfigure` with
# inline values.

terraform {
  backend "gcs" {
    bucket = "gyrinx-staging-tfstate"
    prefix = "gyrinx"
  }
}
