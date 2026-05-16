# staging environment

Wrapper around `../../modules/gyrinx` configured for a (yet-to-be-created)
`gyrinx-staging` GCP project. This is what the team uses to validate the
modules before touching prod.

## Bringing it up

1. Manually create the GCP project `gyrinx-staging` and link billing.
2. Run the bootstrap module against staging:

   ```bash
   cd ../../modules/bootstrap
   terraform init
   terraform apply -var-file=../../environments/staging/bootstrap.tfvars
   ```

3. From this directory, initialise with the GCS backend:

   ```bash
   terraform init
   terraform plan
   ```

4. Iterate on plan until clean, then `terraform apply`.

## Differences from prod

- Smaller Cloud SQL tier (`db-f1-micro`, zonal, no backups).
- Cloud Run scale capped low.
- Uploads bucket has `force_destroy = true`.
- CDN load balancer disabled (no `cdn.gyrinx-staging` DNS to point at it).
