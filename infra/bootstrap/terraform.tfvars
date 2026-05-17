billing_account_id = "01CEC0-B05C50-58A7CD"
region             = "europe-west2"

github_namespace = "gyrinx-app"
github_repo      = "gyrinx"

environments = {
  staging = {
    project_id     = "gyrinx-staging"
    project_name   = "Gyrinx Staging"
    create_project = true
    autodeploy     = false # flip to true once staging is boring
  }
  prod = {
    project_id     = "windy-ellipse-440618-p9"
    create_project = false # prod project already exists (click-ops)
    autodeploy     = false # never auto-deploy prod
  }
}
