# DF-08: Deployment and runtime configuration

| Metadata | Value |
| --- | --- |
| ID | DF-08 |
| Status | Repository-verified pipeline; external trigger, IAM and runtime secret bindings unverified |
| Entry point | Main-branch deployment trigger, cloudbuild.yaml |
| Actors | Source maintainer, Cloud Build and Cloud Run identities; compromised principal ([ADV-05](../adversaries/adv-05-deployment-principal.md)) |
| Assets | [A-08 release](../assets/a-08-release.md), [A-06 service secrets](../assets/a-06-service-secrets.md), [A-02 player data](../assets/a-02-player-data.md) |
| Trust boundaries | TB-02, TB-03, TB-08, TB-09, TB-10 |
| Evidence | [Cloud Build steps](../../../cloudbuild.yaml), [Dockerfile](../../../Dockerfile), [Container startup](../../../docker/entrypoint.sh), [Production settings](../../../gyrinx/settings_prod.py), [Base settings](../../../gyrinx/settings.py), [Deployment overview](../../deployment.md) |

## Sequence

~~~mermaid
sequenceDiagram
    actor Maintainer
    participant Repo as GitHub repository
    participant Build as Cloud Build
    participant Registry as Artifact Registry
    participant Run as Cloud Run Django process
    participant Config as Runtime environment
    participant DB as Cloud SQL
    participant Media as GCS
    Maintainer->>Repo: Merge source to main
    Repo->>Build: Trigger build from revision, crossing TB-08
    Note over Repo,Build: TB-08: repository revision becomes executable build input
    Build->>Registry: Push image tagged by commit SHA
    Build->>Run: Update service to SHA image, crossing TB-09
    Note over Build,Run: TB-09: deployment identity selects production code
    Config->>Run: Supply SECRET_KEY, DB config and provider credentials, crossing TB-10
    Note over Config,Run: TB-10: runtime secret bindings are outside this repository
    Run->>DB: Migrate on startup, then serve app data, crossing TB-02
    Run->>Media: Read and write media objects, crossing TB-03
~~~

## Boundaries and controls

| Boundary | From → to | Data and authority crossing | Current control / assumption |
| --- | --- | --- | --- |
| TB-08 | GitHub → Cloud Build | Source revision and build trigger | Deployment documentation says main changes trigger Cloud Build. Trigger configuration and branch protections are external to this repo and need verification. |
| TB-09 | Cloud Build/registry → Cloud Run | Built image and deploy command | Build pushes an image tagged by COMMIT_SHA and updates Cloud Run to that exact tag. Dockerfile pins Python base and uv image versions; uv sync uses a lockfile. Cloud Build permissions and artifact attestations are external. |
| TB-10 | Runtime configuration → Django | SECRET_KEY, DB_CONFIG, Patreon/Discord/GitHub credentials, service account | settings.py reads these from environment; cloudbuild.yaml does not set or rotate runtime values. Its Secret Manager binding is only for the deploy-notification webhook URL. |
| TB-02 | Cloud Run → Cloud SQL | Migrations and application data | entrypoint runs migrate and ensuresuperuser before Gunicorn. DB access rights and backup policy are external. |
| TB-03 | Cloud Run → GCS | Media object reads and writes | Production storage uses GCS; bucket IAM and CDN policy are external. |

## Failure points

- Source or build-identity compromise can replace the deployed application and reach runtime data and credentials.
- A runtime secret or service-identity compromise can cross directly into database, media or provider APIs.
- Production IAM, trigger settings, image provenance and secret delivery cannot be confirmed from this repository alone; treat any claims about those controls as assumptions until verified in GCP/GitHub configuration.
