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

### Clean up orphaned databases
```bash
./scripts/cleanup-worktree-dbs.sh           # Dry run — list orphans
./scripts/cleanup-worktree-dbs.sh --force   # Drop orphans
```

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
