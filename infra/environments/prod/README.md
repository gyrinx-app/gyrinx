# prod environment

> ⚠️ **Not yet adopted.** Prod was built click-ops and nothing here has been
> applied. The flow for adoption (once staging gives us confidence):
>
> 1. Bootstrap the prod project (state bucket, APIs, AR, terraform-deploy SA).
> 2. `terraform import` every existing resource into state, one by one.
> 3. Run `terraform plan` until it shows no changes.
> 4. Only then start managing prod via Terraform.

Wrapper around `../../modules/gyrinx` for the existing prod project
`windy-ellipse-440618-p9`.

## Names

Names match the existing click-ops resources (`gyrinx-app-bootstrap-*`,
typo and all) so `terraform import` lands cleanly. Don't "fix" the names
here without renaming the underlying resources first.
