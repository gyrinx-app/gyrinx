billing_account_id     = "01CEC0-B05C50-58A7CD"
org_id                 = "533848338530" # gyrinx.app org (same as prod)
region                 = "europe-west2"
spacelift_api_endpoint = "https://gyrinx.app.spacelift.io"

github_namespace = "gyrinx-app"
github_repo      = "gyrinx"

environments = {
  staging = {
    project_id     = "gyrinx-staging"
    project_name   = "Gyrinx Staging"
    create_project = true
    autodeploy     = false # flip to true once staging is boring
  }
  # Prod is intentionally commented out until staging is "boring".
  # Uncomment + re-apply once we're ready to wire the runner SA into prod
  # (see .claude/notes/prod-cutover-plan.md, phase 1).
  #
  # prod = {
  #   project_id     = "windy-ellipse-440618-p9"
  #   create_project = false # prod project already exists (click-ops)
  #   autodeploy     = false # never auto-deploy prod
  # }
}
