output "project_ids" {
  description = "Resolved project ID per environment."
  value       = { for env, cfg in var.environments : env => cfg.project_id }
}

output "spacelift_service_account_emails" {
  description = "Spacelift service account email per environment."
  value       = { for env, sa in google_service_account.spacelift : env => sa.email }
}

output "stack_ids" {
  description = "Spacelift stack IDs per environment."
  value       = { for env, stack in spacelift_stack.env : env => stack.id }
}

output "next_steps" {
  description = "Operator follow-up after first apply."
  value       = <<-EOT
    1. For each environment without a JSON key on disk, run:
         scripts/setup-keys.sh <env>
       This will create the SA key in GCP and drop the JSON at
       ${var.keys_dir}/spacelift-<env>.json. Re-run `terraform apply`
       afterwards to upload the new key to Spacelift.
    2. Visit each stack in the Spacelift UI and trigger the first run.
    3. Once staging is boring, flip `autodeploy = true` on prod.
  EOT
}
