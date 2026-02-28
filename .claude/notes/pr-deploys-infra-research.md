# PR Deploys Infrastructure Research

Research into the current Gyrinx deployment infrastructure to inform the design of PR preview environments.

## 1. Production Build Pipeline (Cloud Build)

### Trigger
- **Trigger ID**: `bd49e415-bc5c-411a-a19d-ec77599c3ddf`
- **Source**: GitHub repository `gyrinx-app/gyrinx`
- **Branch**: Triggered on pushes to `main`
- **Region**: `europe-west2` (London)

### Cloud Build Steps (`cloudbuild.yaml`)
1. **Cancel Previous Builds** - Cancels any older ongoing builds for the same trigger to ensure sequential deployment
2. **Notify Start** - Sends Discord webhook notification with commit SHA and build ID
3. **Build** - `docker build --no-cache` with tag `$_AR_HOSTNAME/$PROJECT_ID/cloud-run-source-deploy/$REPO_NAME/$_SERVICE_NAME:$COMMIT_SHA`
4. **Push** - Pushes the commit-SHA-tagged image
5. **Tag Latest** - Tags the image as `:latest`
6. **Push Latest** - Pushes the `:latest` tag
7. **Deploy** - `gcloud run services update gyrinx` with the new image, labels for commit-sha/build-id/trigger-id
8. **Notify Deploy** - Sends Discord webhook notification on completion

### Build Configuration
- **Substitutions**:
  - `_AR_HOSTNAME`: `europe-west2-docker.pkg.dev` (Artifact Registry)
  - `_SERVICE_NAME`: `gyrinx`
  - `_DEPLOY_REGION`: `europe-west2`
  - `_PLATFORM`: `managed`
- **Image path**: `europe-west2-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/$REPO_NAME/gyrinx:$COMMIT_SHA`
- **Timeout**: 30 minutes (`1800s`)
- **Queue TTL**: 1 hour (`3600s`)
- **Logging**: `CLOUD_LOGGING_ONLY`

### Artifact Registry
- **Hostname**: `europe-west2-docker.pkg.dev`
- **Repository**: `cloud-run-source-deploy/$REPO_NAME`
- Images tagged with both `$COMMIT_SHA` and `latest`

### Secrets
- **Discord webhook URL**: `projects/$PROJECT_ID/secrets/gyrinx-app-boostrap-discord-webhook-url/versions/latest`

## 2. Docker Configuration

### Dockerfile
- **Base image**: `python:3.12.7-slim`
- **Build steps**:
  1. Create venv at `/opt/venv`, add to PATH
  2. Copy `pyproject.toml`, `requirements.txt`, `scripts/`, `gyrinx/`, `content/`
  3. `pip install --editable .`
  4. Install system deps (`libatomic1` for Node.js)
  5. Copy `package.json`, `package-lock.json`
  6. `nodeenv -p` + `npm install`
  7. `npm run build` (builds frontend assets)
  8. Copy `docker/` directory
- **Entrypoint**: `./docker/entrypoint.sh`
- **Port**: `$PORT` (set by Cloud Run, typically 8080)

### Entrypoint (`docker/entrypoint.sh`)
```bash
manage collectstatic --noinput
manage migrate
manage ensuresuperuser --no-input
daphne -b 0.0.0.0 -p $PORT "gyrinx.asgi:application"
```
- Runs migrations on every startup (potential race condition noted in operational docs)
- Runs collectstatic on every startup
- Creates superuser if needed
- Uses **Daphne** (ASGI server), not gunicorn/uvicorn

## 3. Cloud Run Configuration

### Service Details
- **Service name**: `gyrinx`
- **Region**: `europe-west2`
- **Platform**: managed
- **Labels**: `managed-by=gcp-cloud-build-deploy-cloud-run`, `commit-sha`, `gcb-build-id`, `gcb-trigger-id`

### Scaling (from docs/deployment.md)
- Min instances: 0 (scales to zero)
- Max instances: 10
- Container concurrency: 80
- Timeout: 900s
- CPU: 2 cores
- Memory: 2Gi
- CPU throttling: false (always-on CPU)

### Cloud Run Jobs
- `gyrinx-dumpdata` - Exports content library data to GCS bucket `gyrinx-app-bootstrap-dump`

## 4. Database Configuration

### Cloud SQL
- **Instance**: `gyrinx-app-bootstrap-db`
- **Type**: PostgreSQL (version 16.4 used locally)
- **Region**: europe-west2

### Connection Settings (from `settings.py`)
- **DB_CONFIG**: JSON env var with `user` and `password` keys
- **DB_NAME**: env var, default `gyrinx`
- **DB_HOST**: env var, default `localhost`
- **DB_PORT**: env var, default `5432`
- **Engine**: `django.db.backends.postgresql`
- **Driver**: `psycopg2-binary`

### For PR Deploys - Key Considerations
- Production uses Cloud SQL with connection via Cloud SQL Auth Proxy (implied by `DB_HOST` env var)
- Migrations run on container startup via entrypoint
- Content library data is managed in production and synced via `dumpdata`/`loaddata_overwrite`
- The `loaddata_overwrite` command uses `TRUNCATE CASCADE` and `SET session_replication_role = 'replica'` for fast import

## 5. Static Files and Media Handling

### Static Files
- **Dev**: WhiteNoise with `StaticFilesStorage`
- **Prod**: WhiteNoise with `CompressedManifestStaticFilesStorage`
- **Static root**: `BASE_DIR / "staticfiles"`
- **WhiteNoise root**: `BASE_DIR / "static"`
- `collectstatic` runs on container startup

### Media Files (User Uploads)
- **Dev**: Local filesystem (`MEDIA_URL = "/media/"`, `MEDIA_ROOT = BASE_DIR / "media"`)
- **Prod**: Google Cloud Storage via `django-storages`
  - **Bucket**: `gyrinx-app-bootstrap-uploads`
  - **CDN domain**: `cdn.gyrinx.app`
  - **ACLs**: Disabled (uniform access)
  - **Cache-Control**: `public, max-age=2592000` (30 days)
  - `GS_QUERYSTRING_AUTH = False` (public read)

### CDN Setup
- Backend bucket: `gyrinx-uploads-backend`
- URL map: `gyrinx-cdn`
- SSL certificate: `gyrinx-cdn-cert` for `cdn.gyrinx.app`
- HTTPS proxy: `gyrinx-cdn-proxy`
- Forwarding rule: `gyrinx-cdn-https`

## 6. Domain and DNS Setup

- **Main domain**: `gyrinx.app`
- **CDN domain**: `cdn.gyrinx.app`
- **SSL**: Cloud Run provides automatic SSL for the main domain; CDN has its own managed SSL certificate
- **Load Balancer**: In front of Cloud Run with CDN capabilities
- **ALLOWED_HOSTS**: Configured via `ALLOWED_HOSTS` env var (JSON array)
- **CSRF_TRUSTED_ORIGINS**: Configured via `CSRF_TRUSTED_ORIGINS` env var (JSON array)
- **CSRF_COOKIE_DOMAIN**: Configurable via env var
- **BASE_URL**: `https://gyrinx.app` (set in `settings_prod.py`)

## 7. Pub/Sub and Task Queue Configuration

### Architecture
- **Backend**: Custom `PubSubBackend` at `gyrinx.tasks.backend`
- **Push handler**: `/tasks/pubsub/` endpoint receives push messages
- **Per-task topics**: Each task gets its own Pub/Sub topic
- **Topic naming**: `{env}--gyrinx.tasks--{full.module.path}` (e.g., `prod--gyrinx.tasks--gyrinx.core.tasks.refresh_list_facts`)
- **Subscriptions**: `{topic_name}-sub` with push config pointing to service URL

### Registered Tasks
1. `hello_world`
2. `refresh_list_facts`

### Task Provisioning
- Auto-provisions topics, subscriptions, and Cloud Scheduler jobs on startup
- Uses OIDC authentication for push subscriptions
- Service account: `pubsub-invoker@{project_id}.iam.gserviceaccount.com`
- Push endpoint configured with `CLOUD_RUN_SERVICE_URL` env var
- Subscription config includes retry policy and ack deadlines
- Orphaned scheduler jobs are automatically cleaned up

### Cloud Scheduler
- Location: `europe-west2`
- Job naming: `{env}--gyrinx-scheduler--{task-path-with-hyphens}`
- Retry config: 3 retries, 5s-300s backoff

### Environment Variable
- `TASKS_ENVIRONMENT`: Controls topic/job naming prefix (`dev`, `staging`, `prod`)
- Set to `prod` in `settings_prod.py`

## 8. Environment Variables and Secrets Management

### Core Django
- `SECRET_KEY` - Django secret key
- `DJANGO_SETTINGS_MODULE` - Settings module path (prod uses `gyrinx.settings_prod`)
- `DEBUG` - False in production
- `ALLOWED_HOSTS` - JSON array of allowed hosts
- `CSRF_TRUSTED_ORIGINS` - JSON array of trusted origins
- `CSRF_COOKIE_DOMAIN` - Cookie domain

### Database
- `DB_CONFIG` - JSON with `user` and `password`
- `DB_NAME` - Database name
- `DB_HOST` - Database host
- `DB_PORT` - Database port

### Email
- `EMAIL_HOST` - SMTP host (default: `smtp.sendgrid.net`)
- `EMAIL_PORT` - SMTP port (default: `587`)
- `EMAIL_USE_TLS` - TLS enabled (default: `True`)
- `EMAIL_HOST_USER` - SMTP username (default: `apikey`)
- `EMAIL_HOST_PASSWORD` - SendGrid API key

### Google Cloud
- `GOOGLE_CLOUD_PROJECT` - GCP project ID (fallback: `windy-ellipse-440618-p9`)
- `GS_BUCKET_NAME` - GCS bucket for uploads
- `CDN_DOMAIN` - CDN domain for media
- `CLOUD_RUN_SERVICE_URL` - Cloud Run service URL for push subscriptions
- `TASKS_SERVICE_ACCOUNT` - Service account for Pub/Sub OIDC
- `SCHEDULER_LOCATION` - Cloud Scheduler region

### Feature Flags
- `FEATURE_LIST_ACTION_CREATE_INITIAL` - Feature toggle
- `FEATURE_FACTS_FALLBACK_ENQUEUE` - Background task toggle
- `GYRINX_DEBUG` - App debug mode (separate from Django DEBUG)
- `SHOW_BETA_BADGE` - Show beta badge in UI

### External Services
- `GOOGLE_ANALYTICS_ID` - Google Analytics tracking ID
- `PATREON_HOOK_SECRET` - Patreon webhook secret
- `RECAPTCHA_PUBLIC_KEY` / `RECAPTCHA_PRIVATE_KEY` - reCAPTCHA keys
- `TRACING_MODE` - Tracing backend (`off`, `console`, `gcp`)

### Secrets in Cloud Build
- Discord webhook URL stored in Secret Manager: `projects/$PROJECT_ID/secrets/gyrinx-app-boostrap-discord-webhook-url`

## 9. Authentication and Security

- **Auth**: django-allauth with email verification
- **MFA**: TOTP-based via allauth.mfa
- **reCAPTCHA**: On login/signup forms
- **Session**: Secure cookies in production
- **HSTS**: 60 seconds, preload enabled
- **SSL redirect**: Handled by load balancer (not Django)

## 10. GCP Project Details

- **Project ID**: `windy-ellipse-440618-p9`
- **Region**: `europe-west2` (London)
- **Cloud Run service**: `gyrinx`
- **Cloud SQL instance**: `gyrinx-app-bootstrap-db`
- **GCS buckets**:
  - `gyrinx-app-bootstrap-uploads` (user uploads/media)
  - `gyrinx-app-bootstrap-dump` (content library exports)
- **Artifact Registry**: `europe-west2-docker.pkg.dev/{project}/cloud-run-source-deploy/{repo}/gyrinx`

## 11. GitHub Actions / CI

### Workflows
- `format-check.yml` - Runs on PRs and pushes to main; checks Python (ruff), templates (djlint), JS/CSS/JSON (prettier), Jupyter notebooks
- `claude.yml` - Claude Code AI workflow
- `claude-code-review.yml` - AI code review
- `claude-code-improvement.yml` - AI improvement suggestions
- `claude-issue-triage.yml` - AI issue triage
- `weekly-summary.yml` - Weekly summary generation

### Key Observation
- There are NO test-running GitHub Actions workflows in the repository. Tests appear to be run locally or possibly through Cloud Build (though not visible in `cloudbuild.yaml`).
- The format check workflow is the only automated CI check beyond Claude-related workflows.

## 12. Key Implications for PR Deploys

### What a PR Environment Needs
1. **Cloud Run Service**: A separate service per PR (e.g., `gyrinx-pr-{number}`)
2. **Database**: Either a shared staging database or per-PR database
3. **Docker Image**: Built from the PR branch commit
4. **Environment Variables**: All the same env vars, but with PR-specific overrides for:
   - `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` (PR-specific URLs)
   - `CLOUD_RUN_SERVICE_URL` (for task subscriptions)
   - `TASKS_ENVIRONMENT` (to isolate task topics, e.g., `pr-123`)
   - `BASE_URL`
5. **Content Library**: Needs content data loaded (from `gyrinx-app-bootstrap-dump`)
6. **Migrations**: Run automatically on startup (same as prod)
7. **Media/Uploads**: Could point to same prod GCS bucket (read-only) or a test bucket
8. **Pub/Sub**: Task provisioning happens on startup - needs isolation via `TASKS_ENVIRONMENT`

### Challenges
- **Database**: Cloud SQL is expensive per-instance; may need a shared staging DB with per-PR schemas or a single shared database
- **Content Library**: PR environments need content data; could use `loaddata_overwrite` on startup
- **Cleanup**: Need to tear down PR environments when PRs are closed/merged
- **Cost**: Cloud Run + Cloud SQL costs for many concurrent PRs
- **Secrets**: Need to propagate production secrets to PR environments securely
- **DNS/URLs**: Need a way to route `pr-{number}.gyrinx.app` or similar

### Cloud Build Integration
The existing `cloudbuild.yaml` uses `gcloud run services update` which only works for existing services. PR deploys would need `gcloud run deploy` (or `services create`) for new services.

### Entrypoint Implications
The current entrypoint runs `migrate` on every startup. For PR deploys:
- If using a shared database, migrations from PRs could conflict
- If using per-PR databases, migrations run naturally but need content data
- The `ensuresuperuser` command would be useful for PR environments too
