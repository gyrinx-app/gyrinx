project_id        = "gyrinx-staging"
region            = "europe-west2"
environment       = "staging"
state_bucket_name = "gyrinx-staging-tfstate"

# Have bootstrap create the project itself. Drop your billing account ID
# below (find it with `gcloud billing accounts list`). For a personal /
# no-org account, leave org_id and folder_id null.
create_project     = true
project_name       = "Gyrinx Staging"
# billing_account_id = "0X0X0X-0X0X0X-0X0X0X"
# org_id           = null
# folder_id        = null
