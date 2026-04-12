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

Runs the full test suite. Uses Docker if available, otherwise runs pytest directly against local Postgres.

```bash
./scripts/test.sh
```

### `scripts/check_migrations.sh`

Checks for any migration issues or conflicts.

```bash
./scripts/check_migrations.sh
```

## Database Scripts

### `scripts/cleanup-worktree-dbs.sh`

Finds and removes orphaned worktree databases (from deleted worktrees).

```bash
./scripts/cleanup-worktree-dbs.sh           # Dry run — list orphans
./scripts/cleanup-worktree-dbs.sh --force   # Drop orphaned databases
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
