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
# shellcheck source=lib/worktree.sh
source "$SCRIPT_DIR/lib/worktree.sh"

echo "=== Gyrinx Local Postgres Setup ==="
echo

# ---------------------------------------------------------------------------
# 1. Install PostgreSQL 16
# ---------------------------------------------------------------------------
echo "--- [1/8] PostgreSQL 16 ---"
if brew list postgresql@16 &>/dev/null; then
  echo "postgresql@16 already installed."
else
  echo "Installing postgresql@16 via Homebrew..."
  brew install postgresql@16
fi

# Resolve Homebrew paths (works on Apple Silicon and Intel).
PG_BIN_DIR=$(homebrew_postgres_bin)
PG_DATA=$(homebrew_postgres_data_dir)
if [ -z "$PG_BIN_DIR" ]; then
  echo "ERROR: Could not locate postgresql@16 bin directory." >&2
  exit 1
fi
export PATH="$PG_BIN_DIR:$PATH"
# Fall back to deriving PG_DATA from the bin path if the dir doesn't exist yet
# (e.g. fresh install with no cluster initialised).
if [ -z "$PG_DATA" ]; then
  PG_DATA="${PG_BIN_DIR%/opt/postgresql@16/bin}/var/postgresql@16"
fi

# ---------------------------------------------------------------------------
# 2. Initialize cluster with ICU collation (matches Linux glibc behavior)
# ---------------------------------------------------------------------------
echo
echo "--- [2/8] PostgreSQL cluster (ICU collation) ---"

# Only query the cluster's current locale provider if Postgres is actually up.
# Otherwise a transient psql failure would falsely trigger a destructive reinit.
if pg_isready -q 2>/dev/null; then
  CURRENT_PROVIDER=$(psql -d postgres -tAc "SELECT datlocprovider FROM pg_database WHERE datname='postgres'" 2>/dev/null || echo "")
else
  CURRENT_PROVIDER=""
fi

needs_reinit=false
if [ "$CURRENT_PROVIDER" = "i" ]; then
  echo "Cluster already using ICU locale provider."
elif [ "$CURRENT_PROVIDER" = "c" ]; then
  needs_reinit=true
elif [ -z "$CURRENT_PROVIDER" ]; then
  # Postgres isn't running (or psql failed).  Only reinit if PGDATA looks empty.
  # An existing, populated PGDATA almost certainly belongs to the user's
  # current cluster and must not be wiped without confirmation.
  if [ ! -d "$PG_DATA" ] || [ -z "$(ls -A "$PG_DATA" 2>/dev/null || true)" ]; then
    needs_reinit=true
  else
    echo "PGDATA at $PG_DATA exists but Postgres is not running."
    echo "Skipping ICU reinit — start Postgres (\`brew services start postgresql@16\`)"
    echo "and rerun this script to verify the locale provider."
  fi
fi

if [ "$needs_reinit" = true ]; then
  # If PGDATA exists with content we're about to destroy, require explicit
  # confirmation.  This script otherwise wipes the cluster silently when it
  # finds a libc-locale Postgres install, which would be catastrophic for a
  # developer who installed Homebrew Postgres for unrelated work.
  if [ -d "$PG_DATA" ] && [ -n "$(ls -A "$PG_DATA" 2>/dev/null || true)" ]; then
    echo
    echo "WARNING: existing cluster at $PG_DATA uses a non-ICU locale provider."
    echo "Reinitialising will DROP ALL DATABASES in this cluster."
    echo "If you have unrelated Postgres data here, stop now and back it up."
    echo
    if [ "${REINIT_ICU:-}" != "yes" ]; then
      printf "Type 'yes' to wipe and reinitialise: "
      read -r reply
      if [ "$reply" != "yes" ]; then
        echo "Aborted.  Re-run with REINIT_ICU=yes to skip this prompt." >&2
        exit 1
      fi
    fi
  fi
  echo "Reinitializing cluster with ICU locale provider..."
  echo "This ensures sort order matches Linux (Docker, Cloud SQL, CI)."
  brew services stop postgresql@16 2>/dev/null || true
  sleep 1
  rm -rf "$PG_DATA"
  initdb --locale-provider=icu --icu-locale=en-US --encoding=UTF8 --locale=en_US.UTF-8 "$PG_DATA"
  echo "Cluster reinitialized with ICU."
fi

# ---------------------------------------------------------------------------
# 3. Tune PostgreSQL and start the service
# ---------------------------------------------------------------------------
# pytest-xdist with --nomigrations spins up many workers that each create all
# tables via syncdb; the default max_locks_per_transaction (64) is too low and
# tests fail with "out of shared memory".  Mirrors the tuning in
# docker-compose.yml and the GitHub Actions test workflow.
echo
echo "--- [3/8] Tuning + starting PostgreSQL service ---"
PG_CONF="${PG_DATA}/postgresql.conf"
PG_NEEDS_RESTART=false
if [ -f "$PG_CONF" ]; then
  if ! grep -qE '^[[:space:]]*max_locks_per_transaction[[:space:]]*=' "$PG_CONF"; then
    echo "Adding max_locks_per_transaction = 256 to $PG_CONF"
    {
      echo ""
      echo "# Gyrinx: pytest-xdist syncdb across many workers exhausts the default"
      echo "# max_locks_per_transaction (64).  Mirrors CI / docker-compose tuning."
      echo "max_locks_per_transaction = 256"
    } >> "$PG_CONF"
    PG_NEEDS_RESTART=true
  else
    echo "max_locks_per_transaction already tuned in $PG_CONF"
  fi
else
  echo "WARNING: postgresql.conf not found at $PG_CONF — skipping tuning." >&2
fi

if pg_isready -q 2>/dev/null; then
  if [ "$PG_NEEDS_RESTART" = true ]; then
    echo "Restarting PostgreSQL to pick up tuning..."
    brew services restart postgresql@16
  else
    echo "PostgreSQL is already running."
  fi
else
  brew services start postgresql@16
fi

echo "Waiting for PostgreSQL to be ready..."
for i in $(seq 1 30); do
  if pg_isready -q 2>/dev/null; then
    echo "PostgreSQL is ready."
    break
  fi
  sleep 1
done
if ! pg_isready -q 2>/dev/null; then
  echo "ERROR: PostgreSQL did not become ready within 30s." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 3. Install pgAdmin
# ---------------------------------------------------------------------------
echo
echo "--- [4/8] pgAdmin 4 ---"
if [ -d "/Applications/pgAdmin 4.app" ]; then
  echo "pgAdmin 4 already installed."
else
  echo "Installing pgAdmin 4 via Homebrew..."
  brew install --cask pgadmin4
fi

# Write a servers.json describing the local cluster and import it directly
# into pgAdmin's SQLite config via the bundled setup.py CLI.  Avoids the
# "Something went wrong" failure of the GUI Import/Export dialog and
# means the server shows up the next time pgAdmin starts.
PGADMIN_SERVERS_FILE="${HOME}/.gyrinx/pgadmin-servers.json"
mkdir -p "$(dirname "$PGADMIN_SERVERS_FILE")"
cat > "$PGADMIN_SERVERS_FILE" <<JSON
{
  "Servers": {
    "1": {
      "Name": "Gyrinx (local)",
      "Group": "Servers",
      "Host": "localhost",
      "Port": 5432,
      "MaintenanceDB": "postgres",
      "Username": "$(whoami)",
      "SSLMode": "prefer"
    }
  }
}
JSON
echo "Wrote pgAdmin servers config: $PGADMIN_SERVERS_FILE"

PGADMIN_PY="/Applications/pgAdmin 4.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
PGADMIN_SETUP="/Applications/pgAdmin 4.app/Contents/Resources/web/setup.py"
PGADMIN_DB="${HOME}/.pgadmin/pgadmin4.db"
if [ -f "$PGADMIN_DB" ] && [ -x "$PGADMIN_PY" ] && [ -f "$PGADMIN_SETUP" ]; then
  # Skip if a server with the same name already exists, so re-running the
  # setup script is idempotent.
  if sqlite3 "$PGADMIN_DB" "SELECT 1 FROM server WHERE name='Gyrinx (local)' LIMIT 1;" 2>/dev/null | grep -q 1; then
    echo "pgAdmin already has a 'Gyrinx (local)' server — skipping import."
  else
    echo "Importing into pgAdmin's config DB..."
    "$PGADMIN_PY" "$PGADMIN_SETUP" load-servers "$PGADMIN_SERVERS_FILE" \
      --user pgadmin4@pgadmin.org \
      --sqlite-path "$PGADMIN_DB" 2>&1 | tail -3
  fi
else
  echo "pgAdmin not yet initialised — open it once, then re-run this script"
  echo "to register the server automatically."
fi

# ---------------------------------------------------------------------------
# 4. Dump existing Docker database (if available)
# ---------------------------------------------------------------------------
echo
echo "--- [5/8] Checking for existing Docker database ---"
DUMP_FILE=""
if docker info &>/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^postgres$'; then
  echo "Found running Docker Postgres container."
  DUMP_FILE="/tmp/gyrinx_main_docker.dump"
  echo "Dumping Docker 'postgres' database to ${DUMP_FILE}..."
  if docker exec postgres pg_dump -U postgres -Fc postgres > "$DUMP_FILE"; then
    echo "Dump complete ($(du -h "$DUMP_FILE" | awk '{print $1}'))."
  else
    echo "WARNING: docker pg_dump failed. Falling back to fresh database." >&2
    rm -f "$DUMP_FILE"
    DUMP_FILE=""
  fi
else
  echo "No running Docker Postgres found. Will create a fresh database."
fi

# ---------------------------------------------------------------------------
# 5. Create gyrinx_main database
# ---------------------------------------------------------------------------
echo
echo "--- [6/8] Creating gyrinx_main database ---"
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
echo "--- [7/8] Populating database ---"
if [ -n "$DUMP_FILE" ] && [ -f "$DUMP_FILE" ]; then
  # Check if the database has any tables already (i.e. was already restored)
  TABLE_COUNT=$(psql -d gyrinx_main -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
  if [ "$TABLE_COUNT" -gt 0 ]; then
    echo "Database already has ${TABLE_COUNT} tables. Skipping restore."
  else
    echo "Restoring from Docker dump..."
    # pg_restore can emit non-fatal warnings (e.g. role/ACL missing) when
    # --no-owner --no-acl is in effect.  Capture its exit code so genuine
    # failures (e.g. corrupt dump) surface, while still allowing warnings.
    set +o pipefail
    pg_restore --no-owner --no-acl -d gyrinx_main "$DUMP_FILE" 2>&1 | tail -20
    restore_status=${PIPESTATUS[0]}
    set -o pipefail
    if [ "$restore_status" -ne 0 ]; then
      echo "WARNING: pg_restore exited with status $restore_status." >&2
      echo "Some warnings are expected when restoring across Postgres versions." >&2
      echo "Verify the database with: psql -d gyrinx_main -c '\\dt'" >&2
    else
      echo "Restore complete."
    fi
  fi
  rm -f "$DUMP_FILE"
else
  echo "Running migrations on fresh database..."
  export DB_NAME=gyrinx_main
  export DB_HOST=localhost
  export DB_PORT=5432
  export DB_CONFIG=$(db_config_for_local)

  # Activate venv — check local first, then main worktree
  VENV_PATH="${SCRIPT_DIR}/../.venv"
  if [ ! -d "$VENV_PATH" ]; then
    # Try main worktree
    MAIN_WT=$(git -C "${SCRIPT_DIR}" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p' | head -1)
    if [ -n "$MAIN_WT" ] && [ -d "${MAIN_WT}/.venv" ]; then
      VENV_PATH="${MAIN_WT}/.venv"
    fi
  fi
  if [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
  else
    echo "ERROR: No .venv found at ${VENV_PATH}." >&2
    echo "Create one and install the project before running this script:" >&2
    echo "    python -m venv .venv && . .venv/bin/activate && pip install --editable ." >&2
    exit 1
  fi

  manage migrate --no-input
  echo
  echo "Creating superuser..."
  manage ensuresuperuser || manage createsuperuser --no-input 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 8. Wire up per-worktree DB env in venv activation
# ---------------------------------------------------------------------------
# Appending to .venv/bin/activate so `source .venv/bin/activate` from any
# terminal exports DB_NAME / DJANGO_PORT / DB_CONFIG for the current worktree.
# Without this, pytest and `manage` from an interactive shell would fall back
# to settings.py defaults (user=postgres) and fail to connect.
echo
echo "--- [8/8] venv activation hook ---"
VENV_DIR="${SCRIPT_DIR}/../.venv"
if [ ! -d "$VENV_DIR" ]; then
  MAIN_WT=$(git -C "${SCRIPT_DIR}" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p' | head -1)
  if [ -n "$MAIN_WT" ] && [ -d "${MAIN_WT}/.venv" ]; then
    VENV_DIR="${MAIN_WT}/.venv"
  fi
fi
VENV_ACTIVATE="${VENV_DIR}/bin/activate"
HOOK_MARKER="# >>> Gyrinx per-worktree DB env >>>"
if [ ! -f "$VENV_ACTIVATE" ]; then
  echo "No .venv found; skipping hook install."
elif grep -qF "$HOOK_MARKER" "$VENV_ACTIVATE"; then
  echo "Hook already installed in $VENV_ACTIVATE"
else
  cat >> "$VENV_ACTIVATE" <<'BLOCK'

# >>> Gyrinx per-worktree DB env >>>
# Added by scripts/setup-local-postgres.sh.  Makes pytest, manage, and other
# tools target the current worktree's Postgres database without manual exports.
# Re-source the activate script after `cd`ing between worktrees.
_gyrinx_set_db_env() {
  local wt_root lib
  wt_root=$(git rev-parse --show-toplevel 2>/dev/null) || return 0
  lib="$wt_root/scripts/lib/worktree.sh"
  [ -f "$lib" ] || return 0
  # shellcheck source=/dev/null
  source "$lib"
  export DB_NAME
  DB_NAME=$(worktree_db_name "$wt_root")
  export DJANGO_PORT
  DJANGO_PORT=$(worktree_port "$wt_root")
  export DB_HOST=localhost
  export DB_PORT=5432
  export DB_CONFIG
  DB_CONFIG="$(db_config_for_local)"
}
_gyrinx_set_db_env
unset -f _gyrinx_set_db_env
# <<< Gyrinx per-worktree DB env <<<
BLOCK
  echo "Installed hook in $VENV_ACTIVATE"
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
echo "  pgAdmin:   Open pgAdmin 4 from Applications — the 'Gyrinx (local)'"
echo "             server is pre-registered (config at ${PGADMIN_SERVERS_FILE})."
echo "  venv:      Activation now sets per-worktree DB env automatically;"
echo "             re-activate after switching worktrees."
echo
echo "  Next steps:"
echo "    1. Start dev server:  ./scripts/dev.sh"
echo "    2. If fresh DB: populate test data through the app"
echo "    3. Stop Docker Postgres when ready:  docker compose down"
echo
