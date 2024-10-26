# Deployment

## Deployment goals

The goal is that this application is containerised so it can be run in any environment that supports simply deploying a container (e.g. Google Cloud Run).

There should also be a local version that runs in a similar way to the deployment environment so the critical pieces can be tested.

It should be operationally simple for a small team. and secure-by-default.

The components that need to be deployed are:

-   The `gyrinx` Django app
-   A Postgres database

The deployment setup should support configuration by environment variables, as this is widely supported by containerised deployment platforms. This includes management of secrets, so that secret management is deferred to the platform.

Static files should be deployed so that they can be cached.

In future:

-   Our deployment setup should also support production and test environments.
-   The setup should run locally under HTTPS, again to replicate the production environment.

## Implementation

The critical service s the Django app, core containerised functionality and static files.

There could be a `migrations` service that runs `manage migrate` against the database before the application starts, or we could run this in the `Dockerfile` entrypoint for the `app` service.

The application server could be Daphne (partially implemented at time of writing) or Gunicorn. The latter may be more simple.

That the initial URL may use a PaaS domain such as `a.run.app`.

Static files will be served from Django with [Whitenoise](https://whitenoise.readthedocs.io/en/stable/index.html).

### Content Library

The content library is versioned along with the source code. The default answer is to deploy a new version of the content library on each release, but without some thought this would just lead to massive duplication in the database.

One option is to have container do a full import from the content library as it loads, and then perform a cleanup of older and unused content versions. The "live" content version should be stored separately and managed as an admin task.

Here's the process:

-   Collect all JSON schemas and YAML files
-   Validate that the data matches the schema
-   Run the import as a `dry-run` to check for errors (do all of the above in CI too)
-   Run the import against the database with a new version
-   Look for older, unused content library versions and remove them

### Infrastructure

#### Cloud

The default choice for this will be [Google Cloud Run](https://cloud.google.com/run/docs/fit-for-run).

-   [Cloud SQL](https://cloud.google.com/sql?hl=en) or [Neon](https://neon.tech) for Postgres
-   [Cloud Storage](https://cloud.google.com/storage?hl=en) — object store if required, although this may only be for Terraform state and user-uploaded files
-   [Secret Manager](https://cloud.google.com/security/products/secret-manager?hl=en) - secrets
-   [EALB](https://cloud.google.com/load-balancing/docs/https) — load balancing and HTTPS termination [for Cloud Run](https://cloud.google.com/load-balancing/docs/https/setup-global-ext-https-serverless)

Cloud Run autoscales down to zero, which is significant as a cloud cost mitigation factor.

Google will manage [SSL certificates](https://cloud.google.com/load-balancing/docs/ssl-certificates/google-managed-certs).

Auth will most likely be provided by Django built-ins or [Allauth](https://allauth.org/features/).

AWS is the obvious alternative here and would work perfectly well tool (e.g. [Lightsail](https://aws.amazon.com/free/compute/lightsail/)). Cloud Run and Lightsail both have generous free tiers. However, the AWS stack is manifestly more complex than GCP, less well documents, and the authentication primitives in particular are hostile to secure configuration by default. The AWS secure "landing zone" setup is significantly more complex than in GCP.

### Database

CloudSQL with Postgres or Neon. Over the internet is fine for now.

### CI/CD

GitHub Actions as a default — we already have some implemented. Workload Identity Federation to connect GitHub to GCP.

#### IaC

We'll use [Terraform](https://developer.hashicorp.com/terraform/intro) for IaC.

The infrastructure will be configured in a single, separate repo.

Remote state will be managed either in a manually created GCS bucket or in the [HCP Terraform](https://www.hashicorp.com/infrastructure-cloud), to solve the bootstrapping problem.

It may be useful to use config from [Google Cloud Foundation Fabric](https://github.com/GoogleCloudPlatform/cloud-foundation-fabric):

> Fabric FAST was initially conceived to help enterprises quickly set up a GCP organization following battle-tested and widely-used patterns. Despite its origin in enterprise environments, FAST includes many customization points making it an ideal blueprint for organizations of all sizes, ranging from startups to the largest companies.

This gives us a modular approach to the cloud infra primitives, benefiting from the work done in the Google Cloud Foundation team.

#### Logging & Monitoring

Cloud Run is automatically integrated with Cloud Monitoring with no setup or configuration required. This means that metrics of Cloud Run services and jobs are captured automatically when they are running.

At some point, implementing [tracing](https://cloud.google.com/trace/docs/setup#instrumenting_tracing_for_applications) would be advantageous.

### Local implementation

To replicate this setup locally for testing we'll use Docker, and `docker compose` in particular, to create a local cluster of services:

-   `domain.test` — Django application
-   `static.domain.test` — static files

Local HTTPS can be handled by `mkcert` or `minica`. This should not rely on a locally installed copy — probably it should use a containerised version.[[1]](https://letsencrypt.org/docs/certificates-for-localhost/)[[2]](https://github.com/FiloSottile/mkcert)
