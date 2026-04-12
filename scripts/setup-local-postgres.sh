#!/bin/bash
# One-time setup: install local Postgres + pgAdmin and create the gyrinx_main database.
#
# This replaces Docker Postgres for local development.  Run once per machine.
#
# Usage:
#   ./scripts/setup-local-postgres.sh
#
# After running, populate test data through the app or restore from a dump.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Gyrinx Local Postgres Setup ==="
echo

# ---------------------------------------------------------------------------
# 1. Install PostgreSQL 16
# ---------------------------------------------------------------------------
echo "--- [1/6] PostgreSQL 16 ---"
if brew list postgresql@16 &>/dev/null; then
  echo "postgresql@16 already installed."
else
  echo "Installing postgresql@16 via Homebrew..."
  brew install postgresql@16
fi

# Ensure the Homebrew bin is on PATH for this script
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"

# ---------------------------------------------------------------------------
# 2. Initialize cluster with ICU collation (matches Linux glibc behavior)
# ---------------------------------------------------------------------------
echo
echo "--- [2/7] PostgreSQL cluster (ICU collation) ---"
PG_DATA="/opt/homebrew/var/postgresql@16"
CURRENT_PROVIDER=$(psql -d postgres -tAc "SELECT datlocprovider FROM pg_database WHERE datname='postgres'" 2>/dev/null || echo "")

if [ "$CURRENT_PROVIDER" = "i" ]; then
  echo "Cluster already using ICU locale provider."
elif [ "$CURRENT_PROVIDER" = "c" ] || [ -z "$CURRENT_PROVIDER" ]; then
  echo "Reinitializing cluster with ICU locale provider..."
  echo "This ensures sort order matches Linux (Docker, Cloud SQL, CI)."
  brew services stop postgresql@16 2>/dev/null || true
  sleep 1
  rm -rf "$PG_DATA"
  initdb --locale-provider=icu --icu-locale=en-US --encoding=UTF8 --locale=en_US.UTF-8 "$PG_DATA"
  echo "Cluster reinitialized with ICU."
fi

# ---------------------------------------------------------------------------
# 3. Start PostgreSQL service
# ---------------------------------------------------------------------------
echo
echo "--- [3/7] Starting PostgreSQL service ---"
if pg_isready -q 2>/dev/null; then
  echo "PostgreSQL is already running."
else
  brew services start postgresql@16
  echo "Waiting for PostgreSQL to start..."
  for i in $(seq 1 30); do
    if pg_isready -q 2>/dev/null; then
      echo "PostgreSQL is ready."
      break
    fi
    sleep 1
  done
  if ! pg_isready -q 2>/dev/null; then
    echo "ERROR: PostgreSQL failed to start after 30s."
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# 3. Install pgAdmin
# ---------------------------------------------------------------------------
echo
echo "--- [4/7] pgAdmin 4 ---"
if [ -d "/Applications/pgAdmin 4.app" ]; then
  echo "pgAdmin 4 already installed."
else
  echo "Installing pgAdmin 4 via Homebrew..."
  brew install --cask pgadmin4
fi

# ---------------------------------------------------------------------------
# 4. Dump existing Docker database (if available)
# ---------------------------------------------------------------------------
echo
echo "--- [5/7] Checking for existing Docker database ---"
DUMP_FILE=""
if docker info &>/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^postgres$'; then
  echo "Found running Docker Postgres container."
  DUMP_FILE="/tmp/gyrinx_main_docker.dump"
  echo "Dumping Docker 'postgres' database to ${DUMP_FILE}..."
  docker exec postgres pg_dump -U postgres -Fc postgres > "$DUMP_FILE"
  echo "Dump complete ($(du -h "$DUMP_FILE" | awk '{print $1}'))."
else
  echo "No running Docker Postgres found. Will create a fresh database."
fi

# ---------------------------------------------------------------------------
# 5. Create gyrinx_main database
# ---------------------------------------------------------------------------
echo
echo "--- [6/7] Creating gyrinx_main database ---"
CURRENT_USER="$(whoami)"
if psql -lqt | cut -d \| -f 1 | grep -qw gyrinx_main; then
  echo "Database 'gyrinx_main' already exists."
else
  createdb -O "$CURRENT_USER" gyrinx_main
  echo "Created database 'gyrinx_main' (owner: ${CURRENT_USER})."
fi

# ---------------------------------------------------------------------------
# 6. Restore or migrate
# ---------------------------------------------------------------------------
echo
echo "--- [7/7] Populating database ---"
if [ -n "$DUMP_FILE" ] && [ -f "$DUMP_FILE" ]; then
  # Check if the database has any tables already (i.e. was already restored)
  TABLE_COUNT=$(psql -d gyrinx_main -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
  if [ "$TABLE_COUNT" -gt 0 ]; then
    echo "Database already has ${TABLE_COUNT} tables. Skipping restore."
  else
    echo "Restoring from Docker dump..."
    pg_restore --no-owner --no-acl -d gyrinx_main "$DUMP_FILE" 2>&1 | tail -5 || true
    echo "Restore complete."
  fi
  rm -f "$DUMP_FILE"
else
  echo "Running migrations on fresh database..."
  export DB_NAME=gyrinx_main
  export DB_HOST=localhost
  export DB_PORT=5432
  export DB_CONFIG="{\"user\": \"${CURRENT_USER}\", \"password\": \"\"}"

  # Activate venv — check local first, then main worktree
  VENV_PATH="${SCRIPT_DIR}/../.venv"
  if [ ! -d "$VENV_PATH" ]; then
    # Try main worktree
    MAIN_WT=$(git -C "${SCRIPT_DIR}" worktree list 2>/dev/null | head -1 | awk '{print $1}')
    if [ -n "$MAIN_WT" ] && [ -d "${MAIN_WT}/.venv" ]; then
      VENV_PATH="${MAIN_WT}/.venv"
    fi
  fi
  if [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
  fi

  manage migrate --no-input
  echo
  echo "Creating superuser..."
  manage ensuresuperuser || manage createsuperuser --no-input 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo
echo "  Database:  gyrinx_main (port 5432)"
echo "  User:      ${CURRENT_USER} (trust auth, no password)"
echo "  pgAdmin:   Open pgAdmin 4 from Applications"
echo "             Add server: host=localhost, port=5432, user=${CURRENT_USER}"
echo
echo "  Next steps:"
echo "    1. Start dev server:  ./scripts/dev.sh"
echo "    2. If fresh DB: populate test data through the app"
echo "    3. Stop Docker Postgres when ready:  docker compose down"
echo
