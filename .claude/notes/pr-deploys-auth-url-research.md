# PR Deploys: App Configuration, URLs, and Authentication Research

## 1. Every Place in the Codebase That References the Domain/BASE_URL

### Hard-coded Domain References (`gyrinx.app`)

| File | Line | Reference | Type |
|------|------|-----------|------|
| `gyrinx/settings_prod.py` | 49 | `BASE_URL = "https://gyrinx.app"` | Python setting |
| `gyrinx/settings.py` | 63 | `DEFAULT_FROM_EMAIL = "hello@gyrinx.app"` | Email from address |
| `gyrinx/settings.py` | 66 | Comment mentioning `unsubscribe@gyrinx.app` | Comment only |
| `gyrinx/pages/migrations/0001_initial.py` | 12-14 | `domain="gyrinx.app", name="gyrinx.app"` | Django Sites migration (SITE_ID=1) |
| `gyrinx/pages/tests.py` | 18-19 | `site.domain == "gyrinx.app"` | Test assertion |
| `gyrinx/core/templates/core/includes/announcement_banner.html` | 5, 8 | `https://gyrinx.app/beta/`, `https://gyrinx.app/about/` | HTML template hard-coded links |
| `gyrinx/core/migrations/0081_fix_campaign_list_links.py` | 36 | `email="system@gyrinx.app"` | Data migration |

### Dynamic Domain References (Environment Variables)

| Setting | Source | Default | Used For |
|---------|--------|---------|----------|
| `ALLOWED_HOSTS` | `os.getenv("ALLOWED_HOSTS", "[]")` (JSON) | `[]` (prod), `["localhost", "127.0.0.1", "testserver"]` (dev) | Django host validation |
| `CSRF_TRUSTED_ORIGINS` | `os.getenv("CSRF_TRUSTED_ORIGINS", "[]")` (JSON) | `[]` | CSRF origin checking |
| `CSRF_COOKIE_DOMAIN` | `os.environ.get("CSRF_COOKIE_DOMAIN", None)` | `None` | CSRF cookie scoping |
| `BASE_URL` | Hard-coded in `settings_prod.py` | `https://gyrinx.app` | Absolute URL construction |

### URL Construction System

1. **`gyrinx/core/url.py:fullurl()`** - Central utility for building absolute URLs:
   ```python
   def fullurl(request: HttpRequest, path):
       base_url = getattr(settings, "BASE_URL", None)
       if base_url:
           return base_url.rstrip("/") + "/" + path.lstrip("/")
       return request.build_absolute_uri(path)
   ```
   - In production, always uses `BASE_URL` ("https://gyrinx.app")
   - In dev (where `BASE_URL` is not set), falls back to `request.build_absolute_uri()`
   - **Impact for PR deploys**: If `BASE_URL` is set, all generated absolute URLs will point to production. If unset, `build_absolute_uri` will use the request's host, which naturally adapts.

2. **Template tag `{% fullurl %}`** - Used in `gyrinx/core/templatetags/custom_tags.py:264`:
   - Calls `url.fullurl(context["request"], path)`
   - Used in `core/includes/list.html` for sharing URLs and embed URLs

3. **Django Sites Framework** - `SITE_ID = 1`, hardcoded domain `gyrinx.app` in migration.
   - Used by `get_current_site()` in multiple places
   - Used in email templates for `current_site.name` and `current_site.domain`
   - Used by flatpages system

## 2. Authentication Flow and What Breaks with a Different Domain

### Authentication Stack

- **django-allauth** handles all auth (login, signup, email verification, password reset, MFA)
- **Custom adapter**: `gyrinx.core.adapter.CustomAccountAdapter` - controls signups and email headers
- **reCAPTCHA v3** on login, signup, password reset, and username change forms
- **MFA**: TOTP-based, via `allauth.mfa`
- **Session tracking**: `allauth.usersessions` with `USERSESSIONS_TRACK_ACTIVITY = True`

### What Breaks on a Different Domain

1. **Sessions**: `SESSION_COOKIE_SECURE = True` in prod. Sessions are domain-scoped by default. Each PR environment will have its own independent session store (fine since they share the same DB, but users must log in separately per domain).

2. **CSRF**: `CSRF_COOKIE_SECURE = True`, `CSRF_COOKIE_DOMAIN` from env. Must be set to match the PR domain. `CSRF_TRUSTED_ORIGINS` must include the PR environment URL.

3. **reCAPTCHA**: reCAPTCHA keys are domain-bound. If the PR environment is on a different domain/subdomain:
   - The existing reCAPTCHA keys may not work
   - **Solution**: Either register all PR domains with reCAPTCHA, use a wildcard domain, or disable reCAPTCHA in PR environments.
   - Since these are Google reCAPTCHA v3 keys, they can be configured to accept multiple domains in the reCAPTCHA admin console.

4. **Django Sites**: The `Site` object has `domain="gyrinx.app"`. Allauth's email templates use `current_site.name` and `current_site.domain`. Password reset and email verification links will say "gyrinx.app" in emails.
   - **For PR environments**: Not critical since PR environments won't need real email sending (should use console backend).

5. **ALLOWED_HOSTS**: Must include the PR environment hostname.

6. **`safe_redirect()`**: Uses `request.get_host()` for validation - this works correctly with any domain since it's request-relative.

7. **`LOGIN_REDIRECT_URL = "/"`**: Relative path, works on any domain. No issues.

### Authentication Flow for PR Environments with Google IAP

If PR environments are protected by Google IAP:
- IAP authenticates users via Google OAuth before they reach the Django app
- The Django allauth auth system would still be active underneath
- **Two layers of auth**: IAP (Google account) + Django allauth (app account)
- For PR environments, this is acceptable - IAP restricts access to authorized reviewers, while the allauth system can be used normally for testing

## 3. Email Verification and How It Handles Different Domains

### Email Configuration

**Production** (`settings_prod.py`):
- `EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"` via SendGrid
- `DEFAULT_FROM_EMAIL = "hello@gyrinx.app"`
- Custom headers via `EMAIL_EXTRA_HEADERS` env var

**Development** (`settings_dev.py`):
- `EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"` (prints to stdout)
- Can be overridden with `USE_REAL_EMAIL_IN_DEV=True`

### Email Templates and Domain References

Email templates in `gyrinx/core/templates/account/email/`:

- **`base_message.txt`**: Uses `{{ current_site.name }}` and `{{ current_site.domain }}`
- **`email_confirmation_message.txt`**: Uses `{{ current_site.name }}`, `{{ current_site.domain }}`, and `{{ activate_url }}`
- **`password_reset_key_message.txt`**: Uses `{{ password_reset_url }}`

The `activate_url` and `password_reset_url` are generated by allauth using `request.build_absolute_uri()`. The `current_site` references come from `get_current_site(request)` which reads from the Django Sites table.

### Recommendation for PR Environments

- Use console email backend (don't send real emails)
- Set `ACCOUNT_EMAIL_VERIFICATION = "none"` or keep as-is since emails aren't actually sent
- The domain shown in email templates will be `gyrinx.app` from the Sites DB, but this is irrelevant if emails go to console

## 4. Google IAP Setup Requirements and Configuration

### Direct IAP on Cloud Run (Recommended for PR Environments)

Google now supports enabling IAP directly on Cloud Run services without a load balancer.

**Prerequisites**:
- Project must be within a GCP organization
- IAP API enabled (`iap.googleapis.com`)
- Cloud Run API enabled

**Deployment**:
```bash
gcloud beta run deploy SERVICE_NAME \
  --region=REGION \
  --image=IMAGE_URL \
  --no-allow-unauthenticated \
  --iap
```

**Grant IAP Service Agent the Invoker role**:
```bash
gcloud run services add-iam-policy-binding SERVICE_NAME \
  --member=serviceAccount:service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com \
  --role=roles/run.invoker \
  --region=REGION
```

**Restrict access to specific users**:
```bash
gcloud beta iap web add-iam-policy-binding \
  --member=user:USER_EMAIL \
  --role=roles/iap.httpsResourceAccessor \
  --region=REGION \
  --resource-type=cloud-run \
  --service=SERVICE_NAME
```

### Key IAP Considerations for PR Environments

1. **No load balancer needed**: Direct IAP on Cloud Run eliminates the ~$18/month load balancer cost per PR environment.

2. **Domain/URL**: Cloud Run auto-assigned URLs work with IAP. No custom domain needed for PR environments.

3. **Organization restriction**: By default, only users within the same GCP organization can access IAP-protected apps. For external access, additional configuration is needed.

4. **Pub/Sub compatibility**: IAP may interfere with Pub/Sub integrations. PR environments should use the `ImmediateBackend` for tasks instead of `PubSubBackend`.

5. **OAuth consent screen**: Must be configured in the project. Already should exist if the production app is in the same project.

6. **Headers**: IAP adds `X-Goog-Authenticated-User-Email` and `X-Goog-Authenticated-User-ID` headers. Cloud Run also receives `X-Serverless-Authorization`.

### Alternative: Load Balancer-Based IAP

If using the load balancer approach:
- Requires a regional/global external HTTPS load balancer
- Requires a domain name with DNS pointing to the load balancer
- More expensive (~$18/month per LB)
- Auto-assigned Cloud Run URL remains unprotected by IAP
- **Not recommended** for ephemeral PR environments due to cost and complexity

## 5. How ALLOWED_HOSTS and CSRF Work and What Needs to Be Dynamic

### ALLOWED_HOSTS

- **Source**: `os.getenv("ALLOWED_HOSTS", "[]")` parsed as JSON
- **What it does**: Django validates the `Host` header against this list. Requests with unrecognized hosts get 400 errors.
- **For PR environments**: Must include the Cloud Run auto-assigned URL (e.g., `pr-123-gyrinx-xxxxx-ew.a.run.app`)
- **Options**:
  - Set dynamically via env var at deploy time
  - Use wildcard: `[".run.app"]` (allows all Cloud Run URLs)
  - Recommended: Set to the specific service URL, passed as env var during deployment

### CSRF_TRUSTED_ORIGINS

- **Source**: `os.getenv("CSRF_TRUSTED_ORIGINS", "[]")` parsed as JSON
- **What it does**: Lists origins that Django trusts for CSRF. Must be full origins with scheme.
- **For PR environments**: Must include `https://pr-123-gyrinx-xxxxx-ew.a.run.app`
- **Options**:
  - Set dynamically via env var at deploy time
  - Use wildcard: `["https://*.run.app"]`
  - Recommended: Set to the specific service URL, passed as env var during deployment

### CSRF_COOKIE_DOMAIN

- **Source**: `os.environ.get("CSRF_COOKIE_DOMAIN", None)`
- **What it does**: Restricts the CSRF cookie to a specific domain.
- **For PR environments**: Set to `None` (default) or the specific Cloud Run domain. Setting to `None` is safest - the cookie will be scoped to the exact domain.

### SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE

- Both `True` in production
- Cloud Run URLs use HTTPS, so these are fine as-is

### Configuration Strategy

For each PR environment deployment, set these environment variables:
```bash
ALLOWED_HOSTS='["pr-123-service-xxxxx-ew.a.run.app"]'
CSRF_TRUSTED_ORIGINS='["https://pr-123-service-xxxxx-ew.a.run.app"]'
CSRF_COOKIE_DOMAIN=  # Leave unset (None)
```

## 6. Proposed Approach for URL Routing

### Recommended: Cloud Run Auto-Assigned URLs (Simplest)

Each PR environment gets its own Cloud Run service with an auto-assigned URL:
- Format: `https://SERVICE_NAME-xxxxxxxxxx-ew.a.run.app`
- Where `SERVICE_NAME` could be `gyrinx-pr-123`

**Advantages**:
- No DNS configuration needed
- No SSL certificate management
- Auto-assigned by Cloud Run
- Works with IAP directly on Cloud Run
- Each PR is completely isolated

**Implementation**:
1. Deploy a new Cloud Run service per PR: `gyrinx-pr-{PR_NUMBER}`
2. Pass the auto-assigned URL back to GitHub as a deployment URL
3. Set env vars (`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `BASE_URL`) dynamically
4. The `BASE_URL` should be set to the auto-assigned URL (or left unset to use `build_absolute_uri`)

### Alternative: Subdomain-Based (More Complex)

Use subdomains like `pr-123.preview.gyrinx.app`:
- Requires wildcard DNS (`*.preview.gyrinx.app`)
- Requires wildcard SSL certificate
- Requires a load balancer for routing
- **Not recommended** for initial implementation due to complexity and cost

### Key `BASE_URL` Decision

For PR environments, **do NOT set `BASE_URL`** (or set it to the Cloud Run URL). If `BASE_URL` is unset:
- `fullurl()` falls back to `request.build_absolute_uri()` which uses the actual request host
- This naturally adapts to whatever domain the PR is served on
- This is the cleanest approach

If `BASE_URL` must be set (e.g., for generated URLs in async contexts without a request):
- Set it to the Cloud Run auto-assigned URL at deploy time
- Can be done via env var: `BASE_URL=https://gyrinx-pr-123-xxxxxxxxxx-ew.a.run.app`

## 7. Summary of Required Changes for PR Environments

### Settings That Must Be Dynamic (Environment Variables)

| Setting | Current Prod Value | PR Environment Value |
|---------|-------------------|---------------------|
| `ALLOWED_HOSTS` | `["gyrinx.app"]` (from env) | `["PR_SERVICE_URL.run.app"]` |
| `CSRF_TRUSTED_ORIGINS` | `["https://gyrinx.app"]` (from env) | `["https://PR_SERVICE_URL.run.app"]` |
| `CSRF_COOKIE_DOMAIN` | Set from env | `None` (unset) |
| `BASE_URL` | `"https://gyrinx.app"` (hard-coded in settings_prod.py) | Unset, or set to PR URL |
| `DJANGO_SETTINGS_MODULE` | `gyrinx.settings_prod` | `gyrinx.settings_prod` (or a new `settings_pr.py`) |
| `EMAIL_BACKEND` | SMTP (SendGrid) | Console backend |
| `ACCOUNT_ALLOW_SIGNUPS` | `True` | Could be `False` for PR envs |
| `RECAPTCHA_PUBLIC_KEY` | Production key | Empty or test key |
| `RECAPTCHA_PRIVATE_KEY` | Production key | Empty or test key |

### Settings That Already Work (No Changes Needed)

- `LOGIN_REDIRECT_URL = "/"` - relative, works on any domain
- `safe_redirect()` - uses `request.get_host()`, adapts to any domain
- `STATIC_URL = "static/"` - relative, works on any domain
- URL patterns - all relative, work on any domain
- Template URLs - all relative paths
- Session handling - works per-domain by default

### Potential New Settings File: `settings_pr.py`

Could create a `settings_pr.py` that:
1. Imports from `settings_prod.py`
2. Overrides `BASE_URL` to use env var (or unsets it)
3. Sets email to console backend
4. Disables features not needed in PR environments (e.g., Google Analytics, reCAPTCHA)
5. Uses `ImmediateBackend` for background tasks (avoids Pub/Sub conflicts with IAP)

### Hard-coded References That Should Be Addressed

1. **`announcement_banner.html`**: Links to `https://gyrinx.app/beta/` and `https://gyrinx.app/about/` - these are fine for PR environments (link back to production docs)
2. **Sites migration**: Sets domain to `gyrinx.app` - for PR environments, could update via a management command or just leave as-is (only affects email templates)
3. **`DEFAULT_FROM_EMAIL`**: `hello@gyrinx.app` - irrelevant if using console backend

### No CORS Issues

The codebase has no CORS configuration. As a server-rendered Django app (not an SPA), CORS is not applicable.

## 8. Google IAP Integration Architecture

```
User (Google Account) --> Google IAP --> Cloud Run (PR Service) --> Django App

IAP Layer:
- Authenticates via Google OAuth
- Checks IAM roles/iap.httpsResourceAccessor
- Adds X-Goog-Authenticated-User-Email header
- Passes request to Cloud Run

Django Layer:
- Normal Django auth (allauth) still operates
- Two-layer auth: IAP restricts access, Django manages app-level accounts
- PR environments should probably disable signup (ACCOUNT_ALLOW_SIGNUPS=False)
  and pre-create test accounts, or leave signup enabled for testing
```

### IAP Configuration for PR Environments

For each PR Cloud Run service:
1. Enable IAP with `--iap` flag on deploy
2. Set `--no-allow-unauthenticated` (IAP requirement)
3. Grant `roles/iap.httpsResourceAccessor` to specific users/groups
4. Use a Google Group for easier management (e.g., `pr-reviewers@gyrinx.app`)
