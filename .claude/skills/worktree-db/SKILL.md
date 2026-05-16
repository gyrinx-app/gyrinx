---
description: |
  Knowledge about per-worktree database isolation in the Gyrinx project. Load this skill when
  working with databases across worktrees: forking, resetting, migrating, cleaning up orphans,
  or understanding the template workflow. Also useful for pgAdmin setup and database debugging.
---

# Worktree Database Isolation

Each git worktree gets its own Postgres database, forked from a "main" template containing
curated test data (users, lists, campaigns, content packs in various states).

## Database Naming

- **Main worktree**: `gyrinx_main` (the template — manually curated test data)
- **Child worktrees**: `gyrinx_wt_{hash}` (8-char MD5 of absolute worktree path)

All databases live on a single local Postgres instance (port 5432). Isolation is at the
database level, not the server level.

## How Forking Works

Postgres `CREATE DATABASE ... TEMPLATE` does a file-level copy of the template database.
It's fast (seconds for ~50MB) and requires no extensions.

The only constraint: **no active connections** to the template during the copy. `dev.sh`
handles this by calling `pg_terminate_backend()` on template connections before forking.
If the main worktree's Django is running, it briefly disconnects but auto-reconnects.

## Common Operations

### Fork a new database (automatic)
```bash
# dev.sh does this automatically when the DB doesn't exist
./scripts/dev.sh
```

### Reset a worktree database (re-fork from template)
```bash
./scripts/dev.sh --reset-db
# Or manually:
dropdb gyrinx_wt_a1b2c3d4
./scripts/dev.sh
```

### Rebuild a worktree's .venv from scratch
```bash
./scripts/dev.sh --reset-venv   # no-op in the main worktree
```

## Per-Worktree `.venv` (issue #1772)

Each child worktree has its own `.venv` with `gyrinx` editable-installed from
that worktree. Without this, `import gyrinx` would always resolve to the main
worktree's source — silently missing new migrations, new models, etc. The
symptom is `manage migrate` reporting "No migrations to apply" even though the
worktree has a new migration file, or `pytest` failing with `ImportError`
because the imported `gyrinx` doesn't have the worktree's new code.

`./scripts/dev.sh` provisions the venv on first run in a child worktree:

```bash
uv venv "${WT_ROOT}/.venv"
( cd "$WT_ROOT" && uv pip install --python "$WT_VENV/bin/python" --editable . )
```

Then installs the per-worktree DB env hook via
`install_worktree_venv_hook` (from `scripts/lib/worktree.sh`). The main worktree
continues to use whatever venv it already had — provisioning is skipped there.

To verify a venv is worktree-local:
```bash
.venv/bin/python -c "import gyrinx; print(gyrinx.__file__)"
# Should print a path inside the current worktree.
```

### Run migrations on a worktree database
```bash
# dev.sh runs migrate automatically on startup
# Or manually (session hook sets DB_NAME):
manage migrate
```

### Check which database you're using
```bash
source scripts/lib/worktree.sh
echo "DB: $(worktree_db_name)"
# Or check the Django setting:
manage shell -c "from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
```

### Clean up orphaned databases (and pytest test DBs)
```bash
./scripts/cleanup-worktree-dbs.sh                   # Dry run: orphans + their test DBs
./scripts/cleanup-worktree-dbs.sh --force           # Drop orphans + their test DBs
./scripts/cleanup-worktree-dbs.sh --include-tests   # Also list test DBs for active worktrees
./scripts/cleanup-worktree-dbs.sh --include-tests --force
```

## Env Vars for `pytest` / `manage` in an Interactive Terminal

The Claude Code SessionStart hook exports per-worktree DB env vars for every
Bash tool invocation, but a normal interactive terminal needs the same env or
`pytest` / `manage` will fall back to settings.py defaults
(`user=postgres`, `db=gyrinx`) and fail with **"role postgres does not exist"**.

`setup-local-postgres.sh` solves this by appending a block to
`.venv/bin/activate` that exports the right vars on each `source .venv/bin/activate`.

- The hook reads `git rev-parse --show-toplevel` from your `$PWD` at
  activation time, so it picks up the correct worktree even when the venv is
  shared (child worktrees fall back to the main worktree's `.venv`).
- **Re-source the activate script after `cd`ing between worktrees**, otherwise
  you'll still be targeting the previous worktree's DB.
- To reinstall the hook after recreating the venv: `./scripts/setup-local-postgres.sh`
  (the install step is idempotent and guarded by a marker comment).

## Postgres Tuning

`setup-local-postgres.sh` writes `max_locks_per_transaction = 256` into
`postgresql.conf`. The default (64) is too low for `pytest-xdist` with 12
workers each running syncdb in parallel — the symptom is `OperationalError:
out of shared memory` during `django_db_setup`. CI applies the same tuning to
the service-container Postgres in `.github/workflows/test.yaml`, and
`docker-compose.yml` did the same for the old Docker postgres.

## Template Workflow

1. **Initial setup** (once per machine): `./scripts/setup-local-postgres.sh`
   - Installs Postgres + pgAdmin
   - Dumps Docker database → restores as `gyrinx_main`
   - Or creates fresh + migrates

2. **Curate test data** in the main worktree through the app (admin UI, user flows)

3. **New worktrees** automatically fork from `gyrinx_main` via `dev.sh`

4. **Refresh a worktree** after main gets new migrations or test data:
   ```bash
   ./scripts/dev.sh --reset-db
   ```

## pgAdmin

pgAdmin 4 is installed locally (`/Applications/pgAdmin 4.app`). One instance sees all databases:
- **Host**: localhost
- **Port**: 5432
- **User**: your macOS username (trust auth, no password)
- All `gyrinx_main` and `gyrinx_wt_*` databases visible

`setup-local-postgres.sh` pre-registers a "Gyrinx (local)" server by importing
`~/.gyrinx/pgadmin-servers.json` into pgAdmin's SQLite config at
`~/.pgadmin/pgadmin4.db` via the bundled `setup.py load-servers` CLI. The GUI
Import/Export Servers dialog tends to fail with "Something went wrong" on a
fresh install, so we go straight to the config DB.

## Migration Strategies

- **Forward migration**: `dev.sh` runs `manage migrate` on every startup
- **Branch divergence**: If branch A adds 0042_foo and branch B adds 0042_bar, each
  worktree's DB migrates independently. No conflicts since they're separate databases.
- **Backward migration**: Not automated. Drop and re-fork instead:
  `./scripts/dev.sh --reset-db`

## Key Files

- `scripts/lib/worktree.sh` — shared utility functions (DB name, port, label)
- `scripts/dev.sh` — single-command dev startup with auto-fork
- `scripts/setup-local-postgres.sh` — one-time machine setup
- `scripts/cleanup-worktree-dbs.sh` — garbage collection for orphaned DBs
- `scripts/activate_venv_hook.sh` — session hook that auto-sets DB_NAME and DJANGO_PORT
- `gyrinx/settings_dev.py` — reads DJANGO_PORT for dynamic CSRF_TRUSTED_ORIGINS
