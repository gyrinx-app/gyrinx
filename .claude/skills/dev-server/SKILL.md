---
description: |
  Knowledge about starting, stopping, and connecting to the Gyrinx dev server. Load this skill when
  you need to start the dev server, tell Claude in Chrome where to point, check if the server is
  running, or read dev server logs. Also useful when debugging port conflicts or server startup issues.
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
4. Starts `npm run watch` in the background
5. Starts Django `runserver` in the foreground
6. Logs to `./logs/runserver.log` and `./logs/npm-watch.log`

## Port Assignment

- **Main worktree** (`/Users/tom/code/gyrinx/gyrinx`): always port **8000**
- **Child worktrees**: deterministic port derived from path, range **8100-9599**

The port is set via `DJANGO_PORT` environment variable, which is also auto-configured by the
session hook (`scripts/activate_venv_hook.sh`) for every Claude Code Bash invocation.

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

To get the URL without starting the server (e.g. to tell Claude in Chrome):

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
- Claude Code SessionStart hook (`scripts/activate_venv_hook.sh`) — exports them
  into every Claude Code Bash invocation
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

## Telling Claude in Chrome

When Claude in Chrome needs to access the dev server, provide it with the URL from the startup
banner or compute it:

```bash
source scripts/lib/worktree.sh
echo "http://localhost:$(worktree_port)"
```

The CSRF_TRUSTED_ORIGINS in `settings_dev.py` dynamically includes the worktree port, so
form submissions work correctly on any port.
