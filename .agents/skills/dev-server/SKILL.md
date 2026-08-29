---
description: |
  Knowledge about starting, stopping, and connecting to the Gyrinx dev server. Load this skill when
  you need to start the dev server, guide browser use to the right URL, check if the server is
  running, or read dev server logs. Also useful when debugging port conflicts or server startup issues,
  and when an agent needs to log in to the local app for browser testing.
---

# Dev Server

The Gyrinx dev server is started with `scripts/dev.sh`. It handles per-worktree isolation automatically.

## Starting the Server

```bash
./scripts/dev.sh              # Normal startup (runserver + CSS watch)
./scripts/dev.sh --no-watch   # Skip npm watch (if CSS is already built)
./scripts/dev.sh --reset-db   # Drop and re-fork the worktree database, then start
```

This single command:

1. Ensures local Postgres is running
2. Creates/forks the database if needed
3. Runs pending migrations
4. Runs `npm install` if `node_modules` is missing or out of date (vs. `package*.json`)
5. Runs an **initial** `npm run css` build if `styles.css` is missing or stale
6. Starts `npm run watch` in the background (watches scss/html → rebuilds CSS on change)
7. Starts Django `runserver` in the foreground
8. Logs to `./logs/runserver.log`, `./logs/npm-watch.log`, and `./logs/npm-css-build.log`

## Verifying CSS Is Built

**Always confirm CSS exists before relying on the dev server** — `npm run watch` (the watcher) only
rebuilds on file *changes*; it does no initial build, so a fresh worktree without an initial CSS
build will render unstyled pages.

`scripts/dev.sh` now guarantees this for you (steps 4–5 above) and prints a `CSS ready: <path>
(<bytes> bytes)` line plus a `CSS file:` row in the startup banner. Before using the server in a
browser (or otherwise treating it as ready), check that line appeared and that the file is
non-empty:

```bash
CSS=n23/core/static/core/css/styles.css
[ -s "$CSS" ] && echo "CSS OK ($(wc -c <"$CSS") bytes)" || echo "CSS MISSING — re-run scripts/dev.sh"
```

If CSS is missing or you see unstyled pages, the recovery is:

```bash
npm install              # only if node_modules is missing/stale
npm run css              # one-shot initial build
```

Do **not** rely on `npm run watch` alone to produce the first build — it won't.

## Port Assignment

- **Main worktree** (`/Users/tom/code/gyrinx/gyrinx`): always port **8000**
- **Child worktrees**: deterministic port derived from path, range **8100-9599**

The port is set via `DJANGO_PORT` environment variable, which is also auto-configured by the
session hook (`scripts/activate_venv_hook.sh`) for every Agent Bash invocation.

## Finding the URL

The server URL is printed in the startup banner:

```
==========================================
  Gyrinx Dev Server
==========================================
  Worktree:  funny-kalam
  Database:  gyrinx_wt_a1b2c3d4
  URL:       http://localhost:8142
  Logs:      /path/to/worktree/logs/
  CSS watch: running (PID 12345)
==========================================
```

To get the URL without starting the server (e.g. to guide browser use):

```bash
source scripts/lib/worktree.sh
echo "http://localhost:$(worktree_port)"
```

## Checking if the Server is Running

```bash
# Check if Django is listening on the worktree port
source scripts/lib/worktree.sh
PORT=$(worktree_port)
lsof -i :$PORT -sTCP:LISTEN
```

## Log Files

All logs are in the `./logs/` directory (gitignored):

- `runserver.log` — Django runserver output
- `npm-watch.log` — CSS rebuild output

## Environment Variables

Three layers all export the same DB env vars:

- `dev.sh` — exports them in its own shell before launching runserver
- Agent SessionStart hook (`scripts/activate_venv_hook.sh`) — exports them
  into every Agent Bash invocation
- `.venv/bin/activate` hook (installed by `setup-local-postgres.sh`) — exports
  them when the user runs `source .venv/bin/activate` in any terminal

The vars:

- `DB_NAME` — worktree-specific database name
- `DJANGO_PORT` — worktree-specific port
- `DB_HOST=localhost`, `DB_PORT=5432`
- `DB_CONFIG` — local Postgres credentials (trust auth, current macOS user)

Together these mean `manage` and `pytest` automatically target the correct
database in any context.

**Re-source `.venv/bin/activate` after `cd`ing between worktrees** — the venv
hook computes the worktree from `git rev-parse --show-toplevel` at activation
time, not on every command, so the env vars stay pinned to whichever worktree
you activated from until you re-activate.

Symptom of missing env: `pytest` (or `manage`) fails with
`FATAL: role "postgres" does not exist`. That means `DB_CONFIG` isn't set and
`settings.py` defaulted to the production-style `user=postgres`. Fix by
re-activating the venv from the worktree root.

## Guiding browser use

When using a browser to access the dev server, use the URL from the startup banner or compute it:

```bash
source scripts/lib/worktree.sh
echo "http://localhost:$(worktree_port)"
```

The CSRF_TRUSTED_ORIGINS in `settings_dev.py` dynamically includes the worktree port, so
form submissions work correctly on any port.

## Logging in for browser testing

Do **not** submit `/accounts/login/` from an agent session. The form always includes
reCAPTCHA v3 (`gyrinx.account_forms.LoginForm`). Computer-use cannot complete that
challenge, empty `RECAPTCHA_*` keys in `.env` do not skip it, and pytest only passes
because tests mock `django_recaptcha.fields.ReCaptchaField.validate`. Two more traps
sit behind a successful POST: `ACCOUNT_EMAIL_VERIFICATION = "mandatory"`, and
`manage ensuresuperuser` does not create a verified allauth `EmailAddress`.
`/admin/login/` redirects into the same allauth form.

Cloud Agent `.cursor/install.sh` runs `setupenv` but not `ensuresuperuser`, so there
may be no users in the database. Do not guess `tom` / `admin` / the password in `.env`.

Mint a session cookie instead. From the repo root with the venv active (the same
path `scripts/screenshot.py` uses):

```bash
python <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings_dev")
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from allauth.account.models import EmailAddress

User = get_user_model()
username = os.environ.get("AGENT_LOGIN_AS", "agent")
email = f"{username}@localhost"
u, created = User.objects.get_or_create(
    username=username,
    defaults={"email": email, "is_staff": True, "is_superuser": True},
)
if created:
    u.set_password("password")
u.is_staff = True
u.is_superuser = True
if not u.email:
    u.email = email
u.save()
EmailAddress.objects.get_or_create(
    user=u, email=u.email, defaults={"verified": True, "primary": True},
)
client = Client()
client.force_login(u)
cookie = client.cookies[settings.SESSION_COOKIE_NAME]
print(f"{settings.SESSION_COOKIE_NAME}={cookie.value}")
print(f"user={u.username}")
PY
```

`settings_dev.py` names the cookie `gyrinx_sessionid_<DJANGO_PORT>` (and the CSRF
cookie `gyrinx_csrftoken_<port>`) so worktrees on different ports do not overwrite
each other. Setting a cookie called `sessionid` does nothing.

**curl** (replace the name and value with what the snippet printed):

```bash
curl -sS -D - -o /dev/null -b 'gyrinx_sessionid_8000=…' http://localhost:8000/n26/design/ | head
```

A staff session returns `200` on `/n26/design/`; anonymous is `302` to `/accounts/login/`.

**Browser / computer-use:**

1. Open any page on `http://localhost:<port>/` first, so the cookie is set on the
   right origin.
2. In the DevTools console: `document.cookie = "<name>=<value>; path=/";`
3. Navigate to the page under test. Confirm the nav shows the username.

n26's gallery (`/n26/design/…`) and authoring screens are `staff_member_required`.
The snippet sets `is_staff`. To inspect gangs owned by an existing user, rerun it
with `AGENT_LOGIN_AS=<their username>` — `force_login` does not need their password.
