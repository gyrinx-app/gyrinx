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
#   ./scripts/dev.sh                # Normal startup; auto-provisions a
#                                   # per-worktree .venv in child worktrees
#                                   # if missing.
#   ./scripts/dev.sh --no-watch     # Skip npm watch (CSS already built)
#   ./scripts/dev.sh --reset-db     # Drop and re-fork the worktree database
#   ./scripts/dev.sh --reset-venv   # Rebuild the worktree's .venv from scratch
#                                   # (no-op in the main worktree)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/worktree.sh"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
NO_WATCH=false
RESET_DB=false
RESET_VENV=false
for arg in "$@"; do
  case "$arg" in
    --no-watch) NO_WATCH=true ;;
    --reset-db) RESET_DB=true ;;
    --reset-venv) RESET_VENV=true ;;
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

MAIN_WT=$(_main_worktree)

# ---------------------------------------------------------------------------
# Provision per-worktree venv (child worktrees only)
# ---------------------------------------------------------------------------
# Each child worktree gets its own .venv with gyrinx editable-installed from
# that worktree, so `import gyrinx` resolves to worktree-local code (including
# new migrations, new models, etc.).  Without this, every Python invocation
# from a child worktree would resolve gyrinx from the main worktree's editable
# install — see issue #1772.
if [ "$WT_ROOT" != "$MAIN_WT" ]; then
  WT_VENV="${WT_ROOT}/.venv"
  if [ "$RESET_VENV" = true ] && [ -d "$WT_VENV" ]; then
    echo "Removing existing per-worktree venv at $WT_VENV..."
    rm -rf "$WT_VENV"
  fi
  if [ ! -d "$WT_VENV" ]; then
    if ! command -v uv >/dev/null 2>&1; then
      echo "ERROR: \`uv\` is required to provision per-worktree venvs but isn't on PATH." >&2
      echo "Install from https://docs.astral.sh/uv/ or re-create .venv manually:" >&2
      echo "    python -m venv ${WT_VENV} && ${WT_VENV}/bin/pip install --editable ${WT_ROOT}" >&2
      exit 1
    fi
    echo "Provisioning per-worktree venv at $WT_VENV (~1 min)..."
    uv venv "$WT_VENV" >/dev/null
    (
      cd "$WT_ROOT"
      uv pip install --python "$WT_VENV/bin/python" --editable . --quiet
    )
    echo "Provisioned: $WT_VENV"
  fi
  # Always (re-)ensure the activate hook is present.  Idempotent — no-op if
  # the marker is already there.  Catches the case where a child worktree
  # had a .venv from before this change and would otherwise never get the
  # hook installed.
  install_worktree_venv_hook "$WT_VENV/bin/activate" || true
fi

# Activate venv — child worktree's own first, then main worktree as fallback.
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
# Ensure frontend toolchain is installed and CSS is built
# ---------------------------------------------------------------------------
# `node_modules` is gitignored, so child worktrees (and fresh clones) start
# without it. `npm run watch` only rebuilds on file *changes* — it never does
# an initial build — so without these two steps the dev server boots against
# a missing or stale styles.css and templates render unstyled.
CSS_FILE="${WT_ROOT}/gyrinx/core/static/core/css/styles.css"

if [ ! -d "${WT_ROOT}/node_modules" ] \
  || [ "${WT_ROOT}/package-lock.json" -nt "${WT_ROOT}/node_modules" ] \
  || [ "${WT_ROOT}/package.json" -nt "${WT_ROOT}/node_modules" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: \`npm\` is required to build CSS but isn't on PATH." >&2
    exit 1
  fi
  echo "Installing npm dependencies (node_modules missing or out of date)..."
  (cd "$WT_ROOT" && npm install --no-audit --no-fund)
fi

if [ ! -f "$CSS_FILE" ] || [ "${WT_ROOT}/package-lock.json" -nt "$CSS_FILE" ]; then
  echo "Building CSS (initial build)..."
  (cd "$WT_ROOT" && npm run css > "$LOG_DIR/npm-css-build.log" 2>&1) || {
    echo "ERROR: Initial CSS build failed. See $LOG_DIR/npm-css-build.log" >&2
    tail -20 "$LOG_DIR/npm-css-build.log" >&2 || true
    exit 1
  }
fi

if [ ! -s "$CSS_FILE" ]; then
  echo "ERROR: Expected CSS file is missing or empty: $CSS_FILE" >&2
  echo "Run \`npm install && npm run css\` from $WT_ROOT to diagnose." >&2
  exit 1
fi
CSS_SIZE=$(wc -c < "$CSS_FILE" | tr -d ' ')
echo "CSS ready: $CSS_FILE (${CSS_SIZE} bytes)"

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
echo "  CSS file:  ${CSS_FILE} (${CSS_SIZE} bytes)"
if [ "$NO_WATCH" = false ]; then
echo "  CSS watch: running (PID ${PIDS[0]:-?}) → ${LOG_DIR}/npm-watch.log"
fi
echo "=========================================="
echo

# ---------------------------------------------------------------------------
# Start Django runserver (foreground)
# ---------------------------------------------------------------------------
manage runserver "0.0.0.0:${DJANGO_PORT}" 2>&1 | tee "$LOG_DIR/runserver.log"
