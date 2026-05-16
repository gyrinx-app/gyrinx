#!/bin/bash
# Start the Gyrinx development environment.
#
# Handles per-worktree isolation automatically:
#   - Main worktree → gyrinx_main database, port 8000
#   - Child worktrees → forked database, deterministic port
#
# Starts Django runserver + npm watch, logs to ./logs/
#
# Usage:
#   ./scripts/dev.sh              # Normal startup
#   ./scripts/dev.sh --no-watch   # Skip npm watch (CSS already built)
#   ./scripts/dev.sh --reset-db   # Drop and re-fork the worktree database

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/worktree.sh"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
NO_WATCH=false
RESET_DB=false
for arg in "$@"; do
  case "$arg" in
    --no-watch) NO_WATCH=true ;;
    --reset-db) RESET_DB=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve worktree identity
# ---------------------------------------------------------------------------
WT_ROOT=$(_worktree_root)
WT_LABEL=$(worktree_label "$WT_ROOT")
DB_NAME=$(worktree_db_name "$WT_ROOT")
DJANGO_PORT=$(worktree_port "$WT_ROOT")
IS_MAIN=$(_is_main_worktree && echo true || echo false)

export DB_NAME
export DJANGO_PORT
export DB_HOST=localhost
export DB_PORT=5432
export DB_CONFIG="$(db_config_for_local)"
export DJANGO_SETTINGS_MODULE=gyrinx.settings_dev

# Ensure Homebrew Postgres bin is on PATH (Apple Silicon or Intel layout)
PG_BIN_DIR=$(homebrew_postgres_bin)
if [ -n "$PG_BIN_DIR" ]; then
  export PATH="$PG_BIN_DIR:$PATH"
fi

# Activate venv — check worktree first, then main worktree
MAIN_WT=$(_main_worktree)
VENV_PATH="${WT_ROOT}/.venv"
if [ ! -d "$VENV_PATH" ] && [ "$WT_ROOT" != "$MAIN_WT" ]; then
  VENV_PATH="${MAIN_WT}/.venv"
fi
if [ -d "$VENV_PATH" ]; then
  source "$VENV_PATH/bin/activate"
else
  echo "ERROR: No .venv found in ${WT_ROOT} or ${MAIN_WT}." >&2
  echo "Create one from the main worktree before running dev.sh:" >&2
  echo "    python -m venv .venv && . .venv/bin/activate && pip install --editable ." >&2
  exit 1
fi

# Ensure .env exists — copy from main worktree if missing
if [ ! -f "${WT_ROOT}/.env" ] && [ "$WT_ROOT" != "$MAIN_WT" ] && [ -f "${MAIN_WT}/.env" ]; then
  echo "Copying .env from main worktree..."
  cp "${MAIN_WT}/.env" "${WT_ROOT}/.env"
fi

# ---------------------------------------------------------------------------
# Ensure PostgreSQL is running
# ---------------------------------------------------------------------------
if ! pg_isready -q 2>/dev/null; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: PostgreSQL is not running and \`brew\` isn't available." >&2
    echo "Start PostgreSQL manually and re-run \`./scripts/dev.sh\`." >&2
    exit 1
  fi
  echo "Starting PostgreSQL..."
  brew services start postgresql@16
  for i in $(seq 1 30); do
    pg_isready -q 2>/dev/null && break
    sleep 1
  done
  if ! pg_isready -q 2>/dev/null; then
    echo "ERROR: PostgreSQL failed to start."
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Handle --reset-db
# ---------------------------------------------------------------------------
if [ "$RESET_DB" = true ]; then
  if [ "$IS_MAIN" = true ]; then
    echo "ERROR: Cannot reset the main worktree database (it's the template)."
    exit 1
  fi
  if psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    echo "Dropping database '$DB_NAME'..."
    dropdb "$DB_NAME"
  fi
fi

# ---------------------------------------------------------------------------
# Ensure database exists
# ---------------------------------------------------------------------------
db_exists() {
  psql -lqt | cut -d \| -f 1 | grep -qw "$1"
}

if ! db_exists "$DB_NAME"; then
  if [ "$IS_MAIN" = true ]; then
    echo "Creating main database '$DB_NAME'..."
    createdb -O "$(whoami)" "$DB_NAME"
  else
    # Fork from template
    if ! db_exists "gyrinx_main"; then
      echo "ERROR: Template database 'gyrinx_main' does not exist."
      echo "Run ./scripts/setup-local-postgres.sh first (from the main worktree)."
      exit 1
    fi

    echo "Forking database from gyrinx_main -> $DB_NAME..."
    # Terminate connections to the template so CREATE DATABASE ... TEMPLATE works.
    psql -d postgres -c "
      SELECT pg_terminate_backend(pid)
      FROM pg_stat_activity
      WHERE datname = 'gyrinx_main' AND pid <> pg_backend_pid();
    " >/dev/null 2>&1 || true

    createdb -T gyrinx_main -O "$(whoami)" "$DB_NAME"
    echo "Database forked successfully."
  fi
fi

# ---------------------------------------------------------------------------
# Run migrations
# ---------------------------------------------------------------------------
echo "Running migrations on '$DB_NAME'..."
set +o pipefail
manage migrate --no-input 2>&1 | grep -v "^  " | grep -v "^$"
migrate_status=${PIPESTATUS[0]}
set -o pipefail
if [ "$migrate_status" -ne 0 ]; then
  echo "ERROR: Migration failed (exit $migrate_status)."
  exit "$migrate_status"
fi

# ---------------------------------------------------------------------------
# Prepare log directory
# ---------------------------------------------------------------------------
LOG_DIR="${WT_ROOT}/logs"
mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# Background process management
# ---------------------------------------------------------------------------
PIDS=()
cleanup() {
  echo
  echo "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Start npm watch (background)
# ---------------------------------------------------------------------------
if [ "$NO_WATCH" = false ]; then
  echo "Starting npm watch..."
  cd "$WT_ROOT"
  npm run watch > "$LOG_DIR/npm-watch.log" 2>&1 &
  PIDS+=($!)
  cd - >/dev/null
fi

# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------
echo
echo "=========================================="
echo "  Gyrinx Dev Server"
echo "=========================================="
echo "  Worktree:  $WT_LABEL"
echo "  Database:  $DB_NAME"
echo "  URL:       http://localhost:${DJANGO_PORT}"
echo "  Logs:      ${LOG_DIR}/"
if [ "$NO_WATCH" = false ]; then
echo "  CSS watch: running (PID ${PIDS[0]:-?})"
fi
echo "=========================================="
echo

# ---------------------------------------------------------------------------
# Start Django runserver (foreground)
# ---------------------------------------------------------------------------
manage runserver "0.0.0.0:${DJANGO_PORT}" 2>&1 | tee "$LOG_DIR/runserver.log"
