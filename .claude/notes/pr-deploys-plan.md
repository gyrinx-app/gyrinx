# PR Preview Environments: Implementation Plan

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **GCP Org** | Yes, project is in a GCP org | Enables full GCP features |
| **Trigger** | Label-based (`deploy-preview`) | Not every PR needs a preview; saves cost |
| **Access control** | Django auth only (`--allow-unauthenticated`) | Dropping IAP keeps Pub/Sub working; URL is obscure |
| **Background tasks** | Full Pub/Sub (same as production) | Critical for realistic preview behaviour |
| **Email** | Postmark with dev keys (provided separately) | Real email flow for testing; safe sandbox |
| **Media** | Share production GCS bucket | Content images display correctly |
| **DB user** | Same as production | Simpler; PR needs full DDL for migrations anyway |
| **Content freshness** | Weekly dump refresh | Sufficient for PR review purposes |
| **Superuser** | Same credentials as production | Familiar for team; no extra config |

---

## 1. Architecture Overview

```
Developer opens PR -> adds "deploy-preview" label on GitHub
        |
        v
Cloud Build trigger fires (PR event on gyrinx repo)
        |
        v
Build step 0: Check for "deploy-preview" label via GitHub API
  - If absent: exit early (no build)
  - If present: continue
        |
        v
Cloud Build pipeline:
  1. Build Docker image from PR branch
  2. Push image to Artifact Registry
  3. Create PR database on existing Cloud SQL instance (if not exists)
  4. Run migrations + import content snapshot (using built image)
  5. Deploy Cloud Run service: gyrinx-pr-{number}
     - --allow-unauthenticated (Django auth handles access)
     - PR-specific env vars and secrets
     - Pub/Sub provisioning runs on startup via TASKS_ENVIRONMENT=pr-{number}
  6. Post Cloud Run URL as GitHub PR comment
        |
        v
Cloud Run service starts:
  - entrypoint.sh runs: collectstatic, migrate, ensuresuperuser
  - Pub/Sub topics/subscriptions auto-provisioned with pr-{number} prefix
  - Daphne serves the app on auto-assigned URL
  - Django login required (no IAP)
        |
        v
PR closed/merged -> Cleanup (GitHub Actions):
  - Delete Cloud Run service
  - Drop PR database
  - Delete Pub/Sub topics and subscriptions for pr-{number}
  - Clean up Artifact Registry tags
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trigger model | On-demand via `deploy-preview` label | Not every PR needs a preview; saves cost and build time |
| Database | Per-PR database on shared Cloud SQL instance | No new instance cost; complete isolation between PRs |
| URLs | Cloud Run auto-assigned URLs | No DNS, no SSL certs, no load balancer needed |
| Access control | Django auth only (no IAP) | Simpler; allows Pub/Sub push to work; URL is obscure |
| Background tasks | Full PubSubBackend with `TASKS_ENVIRONMENT=pr-{number}` | Realistic preview behaviour; topics isolated by prefix |
| Email | Postmark dev/sandbox account | Real email flow testable; no risk to production reputation |
| Content data | Load from GCS snapshot via `loaddata_overwrite` | Uses existing export infrastructure |
| Build system | Cloud Build (matches production) | Consistent pipeline |

---

## 2. Triggering Mechanism

### How a PR Deploy Is Initiated

**Trigger**: A Cloud Build trigger on the GitHub repository, configured for pull request events.

```bash
gcloud builds triggers create github \
  --name="gyrinx-pr-deploy" \
  --repo-name="gyrinx" \
  --repo-owner="gyrinx-app" \
  --pull-request-pattern="^main$" \
  --build-config="cloudbuild-pr.yaml" \
  --region="europe-west2" \
  --comment-control="COMMENTS_ENABLED"
```

Cloud Build PR triggers fire on every push to the PR branch. The **first step** checks for the `deploy-preview` label via the GitHub API. If absent, the build exits early and costs nothing.

The substitution `_PR_NUMBER` is automatically populated by Cloud Build for PR triggers.

### Cleanup Trigger

A GitHub Actions workflow on `pull_request: closed` events triggers cleanup. GitHub Actions is better suited here because:
- Cloud Build PR triggers don't fire on PR close events
- GitHub Actions has native access to PR metadata
- Cleanup is lightweight (just `gcloud` commands + Pub/Sub teardown)

### Safety Net: Scheduled Orphan Cleanup

A weekly scheduled job finds PR Cloud Run services whose PRs are closed:

```bash
# List PR services
gcloud run services list --region=europe-west2 \
  --filter="metadata.labels.managed-by=pr-deploy" \
  --format="csv[no-heading](metadata.name,metadata.labels.pr-number)"
# Cross-reference each PR number with GitHub API state
# Delete services + databases + Pub/Sub where PR state is "closed"
```

---

## 3. Build Pipeline (`cloudbuild-pr.yaml`)

```yaml
steps:
  # Step 0: Check for "deploy-preview" label
  - name: "gcr.io/google.com/cloudsdktool/cloud-sdk:slim"
    id: "Check Deploy Label"
    entrypoint: bash
    secretEnv: ["_GITHUB_TOKEN"]
    args:
      - -c
      - |
        apt-get update -qq && apt-get install -y -qq jq > /dev/null
        LABELS=$$(curl -sf \
          -H "Authorization: token $$_GITHUB_TOKEN" \
          "https://api.github.com/repos/gyrinx-app/gyrinx/pulls/${_PR_NUMBER}/labels" \
          | jq -r '.[].name')
        if echo "$$LABELS" | grep -q "^deploy-preview$$"; then
          echo "deploy-preview label found. Proceeding with PR deploy."
          echo "DEPLOY=true" > /workspace/deploy_flag
        else
          echo "No deploy-preview label. Skipping."
          echo "DEPLOY=false" > /workspace/deploy_flag
        fi

  # Step 1: Build Docker image
  - name: "gcr.io/cloud-builders/docker"
    id: "Build"
    entrypoint: bash
    args:
      - -c
      - |
        if [ "$$(cat /workspace/deploy_flag)" != "DEPLOY=true" ]; then exit 0; fi
        docker build --no-cache \
          -t $_AR_HOSTNAME/$PROJECT_ID/cloud-run-source-deploy/$REPO_NAME/gyrinx-pr:${_PR_NUMBER}-${SHORT_SHA} \
          -t $_AR_HOSTNAME/$PROJECT_ID/cloud-run-source-deploy/$REPO_NAME/gyrinx-pr:pr-${_PR_NUMBER} \
          -f Dockerfile .
    waitFor: ["Check Deploy Label"]

  # Step 2: Push image
  - name: "gcr.io/cloud-builders/docker"
    id: "Push"
    entrypoint: bash
    args:
      - -c
      - |
        if [ "$$(cat /workspace/deploy_flag)" != "DEPLOY=true" ]; then exit 0; fi
        docker push --all-tags \
          $_AR_HOSTNAME/$PROJECT_ID/cloud-run-source-deploy/$REPO_NAME/gyrinx-pr
    waitFor: ["Build"]

  # Step 3: Create database (if not exists)
  - name: "gcr.io/google.com/cloudsdktool/cloud-sdk:slim"
    id: "Create Database"
    entrypoint: bash
    secretEnv: ["_DB_PASSWORD"]
    args:
      - -c
      - |
        if [ "$$(cat /workspace/deploy_flag)" != "DEPLOY=true" ]; then exit 0; fi
        apt-get update -qq && apt-get install -y -qq postgresql-client > /dev/null
        DB_NAME="gyrinx_pr_${_PR_NUMBER}"
        EXISTS=$$(PGPASSWORD="$$_DB_PASSWORD" psql \
          -h /cloudsql/$_CLOUD_SQL_CONNECTION \
          -U $_DB_USER -d postgres \
          -tAc "SELECT 1 FROM pg_database WHERE datname='$$DB_NAME'")
        if [ "$$EXISTS" != "1" ]; then
          echo "Creating database $$DB_NAME..."
          PGPASSWORD="$$_DB_PASSWORD" psql \
            -h /cloudsql/$_CLOUD_SQL_CONNECTION \
            -U $_DB_USER -d postgres \
            -c "CREATE DATABASE \"$$DB_NAME\";"
        else
          echo "Database $$DB_NAME already exists."
        fi
    waitFor: ["Check Deploy Label"]

  # Step 4: Run migrations and load content
  - name: "$_AR_HOSTNAME/$PROJECT_ID/cloud-run-source-deploy/$REPO_NAME/gyrinx-pr:${_PR_NUMBER}-${SHORT_SHA}"
    id: "Migrate and Load Content"
    entrypoint: bash
    secretEnv: ["_DB_PASSWORD", "_SECRET_KEY"]
    env:
      - "DJANGO_SETTINGS_MODULE=gyrinx.settings_pr"
      - "DB_NAME=gyrinx_pr_${_PR_NUMBER}"
      - "DB_HOST=/cloudsql/${_CLOUD_SQL_CONNECTION}"
      - "DB_PORT=5432"
    args:
      - -c
      - |
        if [ "$$(cat /workspace/deploy_flag)" != "DEPLOY=true" ]; then exit 0; fi
        export DB_CONFIG='{"user":"${_DB_USER}","password":"'"$$_DB_PASSWORD"'"}'
        export SECRET_KEY="$$_SECRET_KEY"
        export ALLOWED_HOSTS='["*"]'
        export CSRF_TRUSTED_ORIGINS='["https://*.run.app"]'

        # Run migrations
        echo "Running migrations..."
        manage migrate --noinput

        # Check if content is already loaded
        CONTENT_COUNT=$$(manage shell -c "from gyrinx.content.models import ContentHouse; print(ContentHouse.objects.count())")
        if [ "$$CONTENT_COUNT" = "0" ]; then
          echo "Loading content data from GCS..."
          gsutil cp gs://gyrinx-app-bootstrap-dump/content-latest.json /tmp/content.json
          manage loaddata_overwrite /tmp/content.json
        else
          echo "Content already loaded ($$CONTENT_COUNT houses found). Skipping."
        fi

        # Ensure superuser exists
        manage ensuresuperuser --no-input
        echo "Migrations and content setup complete."
    waitFor: ["Push", "Create Database"]

  # Step 5: Deploy to Cloud Run
  - name: "gcr.io/google.com/cloudsdktool/cloud-sdk:slim"
    id: "Deploy"
    entrypoint: bash
    args:
      - -c
      - |
        if [ "$$(cat /workspace/deploy_flag)" != "DEPLOY=true" ]; then exit 0; fi
        SERVICE_NAME="gyrinx-pr-${_PR_NUMBER}"

        gcloud run deploy $$SERVICE_NAME \
          --platform=managed \
          --region=$_DEPLOY_REGION \
          --image=$_AR_HOSTNAME/$PROJECT_ID/cloud-run-source-deploy/$REPO_NAME/gyrinx-pr:pr-${_PR_NUMBER} \
          --allow-unauthenticated \
          --set-env-vars="DJANGO_SETTINGS_MODULE=gyrinx.settings_pr" \
          --set-env-vars="DB_NAME=gyrinx_pr_${_PR_NUMBER}" \
          --set-env-vars="DB_HOST=/cloudsql/$_CLOUD_SQL_CONNECTION" \
          --set-env-vars="DB_PORT=5432" \
          --set-env-vars="TASKS_ENVIRONMENT=pr-${_PR_NUMBER}" \
          --set-env-vars="GOOGLE_ANALYTICS_ID=" \
          --set-env-vars="GS_BUCKET_NAME=gyrinx-app-bootstrap-uploads" \
          --set-env-vars="CDN_DOMAIN=cdn.gyrinx.app" \
          --set-env-vars='^##^ALLOWED_HOSTS=["*"]' \
          --set-env-vars='^##^CSRF_TRUSTED_ORIGINS=["https://*.run.app"]' \
          --set-secrets="DB_CONFIG=gyrinx-pr-db-config:latest" \
          --set-secrets="SECRET_KEY=gyrinx-pr-secret-key:latest" \
          --set-secrets="EMAIL_HOST_PASSWORD=gyrinx-pr-email-host-password:latest" \
          --set-secrets="RECAPTCHA_PUBLIC_KEY=gyrinx-pr-recaptcha-public:latest" \
          --set-secrets="RECAPTCHA_PRIVATE_KEY=gyrinx-pr-recaptcha-private:latest" \
          --add-cloudsql-instances=$_CLOUD_SQL_CONNECTION \
          --memory=1Gi \
          --cpu=1 \
          --max-instances=2 \
          --min-instances=0 \
          --timeout=300 \
          --labels="pr-number=${_PR_NUMBER},managed-by=pr-deploy,commit-sha=${SHORT_SHA}" \
          --quiet

        # Get the deployed service URL
        SERVICE_URL=$$(gcloud run services describe $$SERVICE_NAME \
          --region=$_DEPLOY_REGION \
          --format='value(status.url)')
        echo "Deployed: $$SERVICE_URL"
        echo "$$SERVICE_URL" > /workspace/pr_url.txt

        # Update CLOUD_RUN_SERVICE_URL for Pub/Sub push subscriptions
        gcloud run services update $$SERVICE_NAME \
          --region=$_DEPLOY_REGION \
          --set-env-vars="CLOUD_RUN_SERVICE_URL=$$SERVICE_URL" \
          --quiet
    waitFor: ["Migrate and Load Content"]

  # Step 6: Post URL to GitHub PR
  - name: "gcr.io/google.com/cloudsdktool/cloud-sdk:slim"
    id: "Comment on PR"
    allowFailure: true
    entrypoint: bash
    secretEnv: ["_GITHUB_TOKEN"]
    args:
      - -c
      - |
        if [ "$$(cat /workspace/deploy_flag)" != "DEPLOY=true" ]; then exit 0; fi
        apt-get update -qq && apt-get install -y -qq jq > /dev/null
        SERVICE_URL=$$(cat /workspace/pr_url.txt)

        # Delete previous bot comments to avoid spam
        COMMENTS=$$(curl -sf \
          -H "Authorization: token $$_GITHUB_TOKEN" \
          "https://api.github.com/repos/gyrinx-app/gyrinx/issues/${_PR_NUMBER}/comments")
        echo "$$COMMENTS" | jq -r '.[] | select(.body | startswith("**Preview environment")) | .id' | while read cid; do
          curl -sf -X DELETE \
            -H "Authorization: token $$_GITHUB_TOKEN" \
            "https://api.github.com/repos/gyrinx-app/gyrinx/issues/comments/$$cid"
        done

        # Post new comment
        curl -sf -X POST \
          -H "Authorization: token $$_GITHUB_TOKEN" \
          -H "Content-Type: application/json" \
          "https://api.github.com/repos/gyrinx-app/gyrinx/issues/${_PR_NUMBER}/comments" \
          -d "{\"body\": \"**Preview environment deployed** :rocket:\\n\\n$$SERVICE_URL\\n\\nCommit: \`${SHORT_SHA}\`\\nLog in with your Gyrinx account to access.\"}"
    waitFor: ["Deploy"]

  # Step 7: Notify Discord
  - name: "curlimages/curl:latest"
    id: "Notify Discord"
    allowFailure: true
    entrypoint: sh
    secretEnv: ["_WEBHOOK_URL"]
    args:
      - -c
      - |
        if [ "$(cat /workspace/deploy_flag)" != "DEPLOY=true" ]; then exit 0; fi
        SERVICE_URL=$(cat /workspace/pr_url.txt)
        curl -X POST "$$_WEBHOOK_URL" \
          -H "Content-Type: application/json" \
          -d "{\"username\": \"PR Deploy\", \"content\": \"PR #${_PR_NUMBER} preview deployed: $$SERVICE_URL\"}"
    waitFor: ["Deploy"]

substitutions:
  _AR_HOSTNAME: europe-west2-docker.pkg.dev
  _DEPLOY_REGION: europe-west2
  _CLOUD_SQL_CONNECTION: "windy-ellipse-440618-p9:europe-west2:gyrinx-app-bootstrap-db"
  _DB_USER: postgres

availableSecrets:
  secretManager:
    - versionName: projects/$PROJECT_ID/secrets/github-token/versions/latest
      env: "_GITHUB_TOKEN"
    - versionName: projects/$PROJECT_ID/secrets/gyrinx-pr-db-password/versions/latest
      env: "_DB_PASSWORD"
    - versionName: projects/$PROJECT_ID/secrets/gyrinx-pr-secret-key/versions/latest
      env: "_SECRET_KEY"
    - versionName: projects/$PROJECT_ID/secrets/gyrinx-pr-email-host-password/versions/latest
      env: "_EMAIL_HOST_PASSWORD"
    - versionName: projects/$PROJECT_ID/secrets/gyrinx-pr-recaptcha-public/versions/latest
      env: "_RECAPTCHA_PUBLIC"
    - versionName: projects/$PROJECT_ID/secrets/gyrinx-pr-recaptcha-private/versions/latest
      env: "_RECAPTCHA_PRIVATE"
    - versionName: projects/$PROJECT_ID/secrets/gyrinx-app-boostrap-discord-webhook-url/versions/latest
      env: "_WEBHOOK_URL"

options:
  substitutionOption: ALLOW_LOOSE
  logging: CLOUD_LOGGING_ONLY

timeout: 1800s
queueTtl: 3600s

tags:
  - pr-deploy
  - gyrinx
```

### Important Build Pipeline Notes

1. **Cloud SQL in Cloud Build**: Steps that access Cloud SQL use the `/cloudsql/CONNECTION_NAME` socket. The Cloud Build service account needs `roles/cloudsql.client`. Cloud Build automatically starts the Cloud SQL Auth Proxy when `/cloudsql/` paths are used.

2. **Using the built image for migrations (Step 4)**: We run the newly-built Docker image as a Cloud Build step. This ensures migrations match the PR code, not the production code.

3. **Skip-if-no-label pattern**: Every step checks `/workspace/deploy_flag`. This is a workaround because Cloud Build does not support conditional step execution natively. Steps exit immediately with code 0 if the flag is not set.

4. **Two image tags**: Each build tags both `pr-{number}-{sha}` (unique) and `pr-{number}` (mutable, always points to latest build for that PR).

5. **CLOUD_RUN_SERVICE_URL two-pass deploy**: The service URL is only known after deployment. Step 5 deploys first, retrieves the URL, then updates the env var so Pub/Sub push subscriptions point to the correct URL.

---

## 4. Database Setup

### Strategy: Per-PR Database on Shared Cloud SQL Instance

Each PR gets its own PostgreSQL database on the existing `gyrinx-app-bootstrap-db` Cloud SQL instance.

| Aspect | Detail |
|--------|--------|
| Instance | `gyrinx-app-bootstrap-db` (existing, shared with production) |
| Database name | `gyrinx_pr_{pr_number}` (e.g., `gyrinx_pr_42`) |
| User | Same as production |
| Region | europe-west2 |

### Why separate databases (not schemas)

- Django does not natively support PostgreSQL schema switching
- Complete isolation between PRs and production
- Easy to create and drop
- Each PR's migration state is independent

### Creation Flow

```
1. Cloud Build Step 3: Create DB if not exists
   CREATE DATABASE "gyrinx_pr_42";

2. Cloud Build Step 4: Run migrations using PR branch code
   manage migrate --noinput
   (creates all tables from scratch on a fresh DB)

3. Cloud Build Step 4: Check if content exists, load if empty
   manage loaddata_overwrite /tmp/content.json

4. Cloud Build Step 4: Create superuser
   manage ensuresuperuser --no-input
```

On subsequent pushes to the same PR, the database already exists. Migrations run again (applying any new migrations from the latest push), and content loading is skipped since data already exists.

### Teardown

```sql
-- Terminate active connections
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = 'gyrinx_pr_42';
-- Drop the database
DROP DATABASE IF EXISTS "gyrinx_pr_42";
```

---

## 5. Content Library Sync

### Source: GCS Bucket `gyrinx-app-bootstrap-dump`

The existing `gyrinx-dumpdata` Cloud Run Job exports production content. This should produce a `content-latest.json` file.

### Import in PR Environments

During Cloud Build Step 4:

```bash
# Download from GCS
gsutil cp gs://gyrinx-app-bootstrap-dump/content-latest.json /tmp/content.json

# Import using existing command (handles FK disabling, skips Historical tables)
manage loaddata_overwrite /tmp/content.json
```

The `loaddata_overwrite` command:
- Disables FK checks via `SET session_replication_role = 'replica'`
- Truncates existing content tables
- Loads JSON fixture data via Django's `loaddata`
- Skips all Historical model records (audit logs not needed in PR envs)

### Content Freshness

- Refreshed weekly (manually or via scheduled job)
- PR environments created between refreshes may have slightly stale content
- Acceptable for review purposes

### What Gets Imported

- All `content.*` model tables (~45 models)
- All M2M junction tables for content models (~15-20 tables)
- `django_content_type` entries (critical for polymorphic models like ContentMod)

### What Does NOT Get Imported

- Historical* tables (change audit logs -- not needed)
- Core tables (user data -- PR envs start clean)
- Auth/session tables (fresh superuser created by ensuresuperuser)

---

## 6. Cloud Run Service Configuration

### Per-PR Service

| Setting | PR Value | Production |
|---------|----------|------------|
| Service name | `gyrinx-pr-{number}` | `gyrinx` |
| Memory | 1Gi | 2Gi |
| CPU | 1 | 2 |
| Min instances | 0 | 0 |
| Max instances | 2 | 10 |
| Timeout | 300s | 900s |
| Concurrency | 80 | 80 |
| Auth | `--allow-unauthenticated` | `--allow-unauthenticated` |

### Labels

```
pr-number={number}
managed-by=pr-deploy
commit-sha={sha}
```

Labels enable listing and cleaning up PR services with `gcloud run services list --filter`.

### Cloud SQL Connection

```
--add-cloudsql-instances=windy-ellipse-440618-p9:europe-west2:gyrinx-app-bootstrap-db
```

---

## 7. URL/Domain Strategy

### Cloud Run Auto-Assigned URLs

Each PR service gets an auto-assigned URL:
```
https://gyrinx-pr-42-xxxxxxxxxx-ew.a.run.app
```

**Advantages over custom domains:**
- Zero DNS configuration
- Zero SSL certificate management
- Automatic HTTPS
- Free
- Completely isolated per PR

**The URL is only known after deployment.** Cloud Build retrieves it:
```bash
SERVICE_URL=$(gcloud run services describe gyrinx-pr-42 \
  --region=europe-west2 \
  --format='value(status.url)')
```

This URL is posted to the GitHub PR as a comment.

### How the App Handles URLs

The `fullurl()` utility in `gyrinx/core/url.py`:
- If `BASE_URL` is set: uses it as the prefix for absolute URLs
- If `BASE_URL` is empty/unset: falls back to `request.build_absolute_uri()` which uses the request's `Host` header

**For PR environments**: Leave `BASE_URL` empty. All generated URLs naturally use the Cloud Run domain. No code changes needed.

### Hard-coded `gyrinx.app` References (No Changes Needed)

| Location | Reference | Impact |
|----------|-----------|--------|
| `announcement_banner.html` | `https://gyrinx.app/beta/` | Links to prod docs -- correct |
| Django Sites migration | `domain="gyrinx.app"` | Only affects email templates (using Postmark dev account is fine) |
| `DEFAULT_FROM_EMAIL` | `hello@gyrinx.app` | Overridden in `settings_pr.py` |
| `core/migrations/0081` | `system@gyrinx.app` | Data migration, won't run on fresh DB |

---

## 8. Access Control

### No IAP -- Django Auth Only

PR environments are deployed with `--allow-unauthenticated`. Access control is handled entirely by Django's existing authentication system (django-allauth).

**Why no IAP:**
- IAP blocks Pub/Sub push subscriptions (Pub/Sub can't authenticate through IAP)
- We want full Pub/Sub support for realistic preview behaviour
- Django auth is already robust (login required, email verification, MFA)
- The Cloud Run URL is random/obscure and only shared via the PR comment

**What this means:**
- Anyone who discovers the URL can reach the Django login page
- They still need valid Django credentials to access anything useful
- The URL is effectively a shared secret -- only visible in the PR comment
- This matches how many teams handle preview deploys (e.g., Vercel, Netlify)

### reCAPTCHA

Disabled in PR environments (empty keys in `settings_pr.py`). The Cloud Run domain is not registered with reCAPTCHA. Since the URL is obscure, abuse risk is low.

### Superuser

Same credentials as production, created by `ensuresuperuser` on container startup.

---

## 9. App Configuration (`settings_pr.py`)

### New Settings File

```python
# gyrinx/settings_pr.py
"""
Settings for PR preview environments.

Inherits from production settings with overrides for:
- Email (Postmark dev/sandbox account via SMTP)
- BASE_URL (empty, uses request host)
- reCAPTCHA (keys from Secret Manager, prod keys updated for *.run.app)
- Analytics (disabled)
- Tracing (GCP, enabled for debugging)
"""
import os

from .settings_prod import *  # noqa: F403

# Allow BASE_URL from env var, default to empty (fullurl uses build_absolute_uri)
BASE_URL = os.getenv("BASE_URL", "")

# Email: Postmark dev/sandbox account via SMTP
# EMAIL_HOST_PASSWORD provided via gyrinx-pr-email-host-password secret
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "hello@gyrinx.app")

# reCAPTCHA: use production keys (updated to accept *.run.app domains)
# Keys provided via Secret Manager
RECAPTCHA_PUBLIC_KEY = os.getenv("RECAPTCHA_PUBLIC_KEY", "")
RECAPTCHA_PRIVATE_KEY = os.getenv("RECAPTCHA_PRIVATE_KEY", "")

# Disable Google Analytics
GOOGLE_ANALYTICS_ID = ""

# Show beta badge to indicate preview environment
SHOW_BETA_BADGE = True

# Enable GCP tracing for debugging
TRACING_MODE = "gcp"
```

**Note:** Background tasks use the production `PubSubBackend` -- no override needed. The `TASKS_ENVIRONMENT=pr-{number}` env var isolates all topics and subscriptions.

**Important:** The Pub/Sub provisioning code must guard against creating push subscriptions when `CLOUD_RUN_SERVICE_URL` is unset. On the first deploy, this env var is not yet available (it's set in a second update after the URL is known). The provisioning code should skip subscription creation if the URL is empty.

### Environment Variables per PR Service

| Variable | Value | Set By |
|----------|-------|--------|
| `DJANGO_SETTINGS_MODULE` | `gyrinx.settings_pr` | Cloud Build deploy step |
| `DB_NAME` | `gyrinx_pr_{number}` | Cloud Build deploy step |
| `DB_HOST` | `/cloudsql/{connection}` | Cloud Build deploy step |
| `DB_PORT` | `5432` | Cloud Build deploy step |
| `DB_CONFIG` | `{"user":"...","password":"..."}` | Secret Manager (`gyrinx-pr-db-config`) |
| `SECRET_KEY` | Django secret | Secret Manager (`gyrinx-pr-secret-key`) |
| `EMAIL_HOST_PASSWORD` | Postmark dev SMTP token | Secret Manager (`gyrinx-pr-email-host-password`) |
| `RECAPTCHA_PUBLIC_KEY` | Production key (updated for *.run.app) | Secret Manager (`gyrinx-pr-recaptcha-public`) |
| `RECAPTCHA_PRIVATE_KEY` | Production key | Secret Manager (`gyrinx-pr-recaptcha-private`) |
| `ALLOWED_HOSTS` | `["*"]` | Cloud Build deploy step |
| `CSRF_TRUSTED_ORIGINS` | `["https://*.run.app"]` | Cloud Build deploy step |
| `TASKS_ENVIRONMENT` | `pr-{number}` | Cloud Build deploy step |
| `CLOUD_RUN_SERVICE_URL` | Auto-assigned URL | Set after deploy (2nd update) |
| `GS_BUCKET_NAME` | `gyrinx-app-bootstrap-uploads` | Cloud Build deploy step |
| `CDN_DOMAIN` | `cdn.gyrinx.app` | Cloud Build deploy step |
| `GOOGLE_ANALYTICS_ID` | (empty) | Cloud Build deploy step |

### Secret Manager Inventory

| Secret Name | Contents | Notes |
|-------------|----------|-------|
| `gyrinx-pr-secret-key` | Django SECRET_KEY | New, different from prod |
| `gyrinx-pr-db-config` | `{"user":"...","password":"..."}` | Same creds as prod |
| `gyrinx-pr-email-host-password` | Postmark dev SMTP token | You provide |
| `gyrinx-pr-recaptcha-public` | reCAPTCHA v3 site key | Same as prod (updated for *.run.app) |
| `gyrinx-pr-recaptcha-private` | reCAPTCHA v3 secret key | Same as prod |
| `github-token` | Fine-grained GitHub PAT | `pull_requests:read` + `issues:write` |
| `gyrinx-app-boostrap-discord-webhook-url` | Discord webhook | Already exists, reuse |

**Note on `ALLOWED_HOSTS=["*"]`**: Acceptable since the URL is obscure and Django auth handles access control. Could be tightened to the specific Cloud Run URL if preferred.

---

## 10. Pub/Sub and Background Tasks

### Full Pub/Sub Support in PR Environments

PR environments use the same `PubSubBackend` as production. Topic isolation is achieved via the `TASKS_ENVIRONMENT` setting.

### Topic Naming

```
pr-42--gyrinx.tasks--gyrinx.core.tasks.refresh_list_facts
pr-42--gyrinx.tasks--gyrinx.core.tasks.hello_world
```

Each PR gets its own set of topics and subscriptions, completely isolated from production and other PRs.

### How It Works

1. On container startup, the Pub/Sub provisioning code (`gyrinx/tasks/provisioning.py`) auto-creates:
   - Topics for each registered task
   - Push subscriptions pointing to `CLOUD_RUN_SERVICE_URL/tasks/pubsub/`
   - Cloud Scheduler jobs for scheduled tasks (with `pr-{number}` prefix)
2. Push subscriptions use OIDC auth with the `pubsub-invoker` service account
3. Since there's no IAP, push requests can reach the Cloud Run service directly

### CLOUD_RUN_SERVICE_URL Chicken-and-Egg

The Pub/Sub push subscription needs the service URL, but the URL is only known after deployment. This is solved by:
1. Deploy the Cloud Run service (Step 5)
2. Retrieve the auto-assigned URL
3. Update the service with `CLOUD_RUN_SERVICE_URL` env var
4. The next container startup will provision Pub/Sub with the correct URL

On the very first request, Pub/Sub won't be provisioned yet. The entrypoint runs `migrate` and `ensuresuperuser` but doesn't explicitly provision Pub/Sub -- that happens when the first task is enqueued. If provisioning happens during a request, it's a one-time cost.

### Cleanup

When a PR environment is torn down, the Pub/Sub resources must also be cleaned up:

```bash
PR_NUM=42
ENV_PREFIX="pr-${PR_NUM}"

# List and delete topics
gcloud pubsub topics list --format="value(name)" \
  --filter="name:${ENV_PREFIX}--gyrinx.tasks" | while read topic; do
  gcloud pubsub topics delete "$topic" --quiet
done

# List and delete subscriptions
gcloud pubsub subscriptions list --format="value(name)" \
  --filter="name:${ENV_PREFIX}--gyrinx.tasks" | while read sub; do
  gcloud pubsub subscriptions delete "$sub" --quiet
done

# List and delete Cloud Scheduler jobs
gcloud scheduler jobs list --location=europe-west2 \
  --format="value(name)" \
  --filter="name:${ENV_PREFIX}" | while read job; do
  gcloud scheduler jobs delete "$job" --location=europe-west2 --quiet
done
```

### Required Permissions

The Cloud Run service account needs:
- `roles/pubsub.editor` (to create topics and subscriptions)
- `roles/cloudscheduler.admin` (to create scheduler jobs)
- These should already be granted if production uses the same service account

---

## 11. Cleanup / Teardown

### Automatic: GitHub Actions on PR Close

```yaml
# .github/workflows/pr-deploy-cleanup.yml
name: PR Deploy Cleanup

on:
  pull_request:
    types: [closed]

jobs:
  cleanup:
    runs-on: ubuntu-latest
    if: contains(github.event.pull_request.labels.*.name, 'deploy-preview')
    steps:
      - name: Authenticate to GCP (service account key)
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
          # SA needs: roles/run.admin, roles/cloudsql.client, roles/pubsub.editor,
          # roles/cloudscheduler.admin, roles/artifactregistry.writer

      - name: Setup gcloud
        uses: google-github-actions/setup-gcloud@v2

      - name: Delete Cloud Run service
        run: |
          gcloud run services delete "gyrinx-pr-${{ github.event.pull_request.number }}" \
            --region=europe-west2 --quiet || echo "Service not found"

      - name: Drop PR database
        run: |
          PR_NUM=${{ github.event.pull_request.number }}
          gcloud sql connect gyrinx-app-bootstrap-db \
            --user=postgres --quiet \
            --database=postgres <<EOF
          SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = 'gyrinx_pr_${PR_NUM}';
          DROP DATABASE IF EXISTS "gyrinx_pr_${PR_NUM}";
          EOF

      - name: Clean up Pub/Sub resources
        run: |
          PR_NUM=${{ github.event.pull_request.number }}
          ENV_PREFIX="pr-${PR_NUM}"

          # Delete topics
          gcloud pubsub topics list --format="value(name)" \
            --filter="name:${ENV_PREFIX}--gyrinx.tasks" 2>/dev/null | while read topic; do
            gcloud pubsub topics delete "$topic" --quiet
          done

          # Delete subscriptions
          gcloud pubsub subscriptions list --format="value(name)" \
            --filter="name:${ENV_PREFIX}--gyrinx.tasks" 2>/dev/null | while read sub; do
            gcloud pubsub subscriptions delete "$sub" --quiet
          done

          # Delete scheduler jobs
          gcloud scheduler jobs list --location=europe-west2 \
            --format="value(name)" \
            --filter="name:${ENV_PREFIX}" 2>/dev/null | while read job; do
            gcloud scheduler jobs delete "$job" --location=europe-west2 --quiet
          done

      - name: Clean up Docker images
        run: |
          gcloud artifacts docker tags delete \
            "europe-west2-docker.pkg.dev/windy-ellipse-440618-p9/cloud-run-source-deploy/gyrinx/gyrinx-pr:pr-${{ github.event.pull_request.number }}" \
            --quiet 2>/dev/null || true
```

### Scheduled Orphan Cleanup (Safety Net via GitHub Actions Cron)

A weekly GitHub Actions cron job (e.g. Sundays at midnight) that:
1. Lists all Cloud Run services with label `managed-by=pr-deploy`
2. For each, checks if the corresponding PR is still open via `gh pr view`
3. Deletes services + databases + Pub/Sub for closed PRs

```yaml
# Add to pr-deploy-cleanup.yml
on:
  pull_request:
    types: [closed]
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday
```

The scheduled run iterates over all PR services and runs the same cleanup steps for any whose PR is closed.

---

## 12. Cost Estimate

### Per PR Environment

| Resource | Cost When Active | Cost When Idle | Notes |
|----------|-----------------|----------------|-------|
| Cloud Run | ~$1-5/month | $0 | Scales to zero; pay per request |
| Cloud SQL storage | ~$0.02/month | ~$0.02/month | ~100MB per PR DB on shared instance |
| Artifact Registry | ~$0.05 | ~$0.05 | ~500MB per image |
| Pub/Sub | ~$0.01/month | $0 | Minimal messages for PR usage |
| Cloud Scheduler | Free | Free | 3 free jobs per account |
| Cloud Build | ~$0.003/build min | N/A | ~10-15 min per build |

### Estimated Monthly Total

- **5 concurrent PR environments, light usage**: $2-10/month
- **Key savings**: No new Cloud SQL instances, no load balancers, scales to zero

---

## 13. Phased Implementation Plan

### Phase 1: Settings and Infrastructure Prep

**Goal**: Create `settings_pr.py`, add Pub/Sub safety guard, and set up GCP prerequisites.

1. Create `gyrinx/settings_pr.py` (as described in Section 9)
2. Add safety guard to Pub/Sub provisioning: skip push subscription creation when `CLOUD_RUN_SERVICE_URL` is unset/empty
3. Test locally: `DJANGO_SETTINGS_MODULE=gyrinx.settings_pr manage runserver`
   - Verify `fullurl()` generates localhost URLs (no `BASE_URL`)
   - Verify tracing mode is `gcp`
   - Verify Pub/Sub provisioning respects the safety guard
4. Ensure the `gyrinx-dumpdata` job produces `content-latest.json` in GCS
5. Update reCAPTCHA site config to accept `*.run.app` domains
6. Create Secret Manager secrets (see inventory in Section 9):
   - `gyrinx-pr-secret-key`, `gyrinx-pr-db-config`, `gyrinx-pr-email-host-password`
   - `gyrinx-pr-recaptcha-public`, `gyrinx-pr-recaptcha-private`
   - `github-token` (fine-grained PAT: `pull_requests:read` + `issues:write`)
7. Grant Cloud Build service account `roles/cloudsql.client`
8. Create `deploy-preview` label in the GitHub repository

### Phase 2: Manual Cloud Build Deploy

**Goal**: Get a single PR environment deployed via manual Cloud Build trigger.

1. Create `cloudbuild-pr.yaml` (as described in Section 3)
2. Test manually:
   ```bash
   gcloud builds submit . \
     --config=cloudbuild-pr.yaml \
     --substitutions="_PR_NUMBER=test-1" \
     --region=europe-west2
   ```
3. Verify: image builds, database created, migrations run, content loaded, service deploys
4. Test accessing the deployed service and logging in
5. Verify Pub/Sub topics are created with `pr-test-1` prefix
6. Fix any issues with Cloud SQL connectivity, env vars, or content loading

### Phase 3: Automated Triggers + Cleanup

**Goal**: Automate the full PR deploy/cleanup lifecycle.

1. Create Cloud Build trigger for PR events
2. Test: push to a PR with `deploy-preview` label -> build triggers -> service deploys
3. Test: push to a PR without `deploy-preview` label -> build exits early
4. Create `.github/workflows/pr-deploy-cleanup.yml`
5. Test: close PR -> service deleted, database dropped, Pub/Sub cleaned up
6. Test full lifecycle: open PR -> label -> deploy -> push update -> redeploy -> close -> cleanup

### Phase 4: Polish

**Goal**: Add observability and safety nets.

1. Add Discord notifications for PR deploys
2. Set up scheduled orphan cleanup (weekly)
3. Test edge cases: concurrent PR deploys, database already exists, service already exists
4. Document the system

---

## 14. Remaining Open Questions

These are implementation details to be resolved during Phase 1-2:

1. **Content export format**: Does the existing `gyrinx-dumpdata` job produce output compatible with `loaddata_overwrite`? Need to verify the filename and format in GCS.

2. **Cloud SQL in Cloud Build**: Need to confirm the Cloud Build service account has `roles/cloudsql.client` and that the `/cloudsql/` socket path works in build steps.

3. **Pub/Sub service account**: Does the existing `pubsub-invoker` service account work for PR environments, or does it need additional configuration for the PR Cloud Run service URL?

4. **Cloud SQL capacity**: How many concurrent PR databases can the existing instance handle? Each adds ~100MB storage. Need to check connection limits.

### Items Requiring User Action

These need to be provided/done before implementation can proceed:

- [ ] **Postmark dev SMTP token** -> store as `gyrinx-pr-email-host-password` in Secret Manager
- [ ] **GitHub fine-grained PAT** (`pull_requests:read` + `issues:write`) -> store as `github-token`
- [ ] **Update reCAPTCHA site config** to accept `*.run.app` domains
- [ ] **GCP service account key** for GitHub Actions -> store as `GCP_SA_KEY` GitHub secret
- [ ] **Create `deploy-preview` label** in the GitHub repository
