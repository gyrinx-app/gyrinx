# prod environment

> ⚠️ **Not yet adopted.** Prod was built click-ops and nothing here
> has been applied. The path to adoption (once staging is boring):
>
> 1. `terraform import` every existing resource into the prod stack's
>    state via Spacelift's "Tasks" feature, one by one.
> 2. Watch `terraform plan` shrink to zero.
> 3. Only then start managing prod via this stack.

Wrapper around `../../modules/gyrinx` for the existing prod project
`windy-ellipse-440618-p9`. **Managed by Spacelift** (stack
`gyrinx-prod`).

State is stored by Spacelift; no backend.tf.

## Names

Names match the existing click-ops resources (`gyrinx-app-bootstrap-*`,
typo and all) so `terraform import` lands cleanly. Don't "fix" the
names here without renaming the underlying resources first.

## Auto-deploy

`autodeploy = false` is non-negotiable for prod. Every apply requires
manual confirm in the Spacelift UI.
