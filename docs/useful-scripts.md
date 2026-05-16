# Useful Scripts

This document provides an overview of commonly used scripts in the Gyrinx project.

## Development Scripts

### `scripts/dev.sh`

Starts the full development environment with a single command. Handles per-worktree database isolation automatically: ensures the database exists (forking from the `gyrinx_main` template if needed), runs migrations, starts Django `runserver` and `npm run watch` for CSS rebuilds.

```bash
./scripts/dev.sh              # Normal startup
./scripts/dev.sh --no-watch   # Skip CSS watcher
./scripts/dev.sh --reset-db   # Drop and re-fork the worktree database
```

### `scripts/setup-local-postgres.sh`

One-time setup: installs PostgreSQL 16 and pgAdmin via Homebrew, initialises the database cluster with ICU collation (matching Linux/production sort behaviour), and creates the `gyrinx_main` development database. If Docker Postgres is running, it dumps and restores from it automatically.

```bash
./scripts/setup-local-postgres.sh
```

### `scripts/fmt.sh`

Formats all code in the project including Python, JavaScript, SCSS, and Django templates.

```bash
./scripts/fmt.sh
```

### `scripts/test.sh`

Thin wrapper over `pytest` against the local Postgres database. `pyproject.toml`
already enables parallel execution (`-n auto`) and `--nomigrations` via addopts,
so the bare invocation runs the full suite in parallel and rebuilds the test
DB from current model definitions on every run.

```bash
./scripts/test.sh                  # full suite, parallel
./scripts/test.sh -n 0             # serial
./scripts/test.sh gyrinx/core/     # a directory
./scripts/test.sh -k campaign      # by name
```

### `scripts/check_migrations.sh`

Checks for any migration issues or conflicts.

```bash
./scripts/check_migrations.sh
```

## Database Scripts

### `scripts/cleanup-worktree-dbs.sh`

Finds and removes orphaned worktree databases (from deleted worktrees) along
with their pytest test databases. Pass `--include-tests` to also clean up
test DBs for *active* worktrees — pytest will recreate them on next run, so
this is a safe way to reclaim disk.

```bash
./scripts/cleanup-worktree-dbs.sh                   # Dry run: orphans only
./scripts/cleanup-worktree-dbs.sh --force           # Drop orphans
./scripts/cleanup-worktree-dbs.sh --include-tests   # Dry run + active test DBs
./scripts/cleanup-worktree-dbs.sh --include-tests --force
```

### `scripts/reset-migrations-to-main.sh`

Safely resets Django migration state to match the main branch. Useful when switching between branches with different migration histories.

```bash
./scripts/reset-migrations-to-main.sh
```

## Quality Assurance Scripts

### `scripts/fmt-check.sh`

Checks if code formatting is correct without making changes.

```bash
./scripts/fmt-check.sh
```

## Management Commands

These are Django management commands available through the `manage` command:

### `manage setupenv`

Sets up the development environment file (.env).

```bash
manage setupenv
```

### `manage ensuresuperuser`

Ensures a superuser exists for development.

```bash
manage ensuresuperuser
```

### `manage loaddata_overwrite`

Loads Django fixtures with overwrite capability.

```bash
manage loaddata_overwrite <fixture_name>
```
