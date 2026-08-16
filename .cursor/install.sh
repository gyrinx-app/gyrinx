#!/usr/bin/env bash
#
# Cloud Agent install script for Gyrinx.
#
# Runs after the repository is checked out. Idempotent: every step is a no-op
# when it has already been done, so it is safe to re-run (and to run against a
# build snapshot that already has most of this in place).
#
# System services (PostgreSQL) are STARTED here only so migrations can run; the
# per-boot start lives in .cursor/start.sh.

set -euo pipefail

# Always operate from the repository root (the dir that contains this .cursor/).
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { echo "=== $* ==="; }

# ---------------------------------------------------------------------------
# 1. uv — manages the Python interpreter (3.14, per .python-version) and deps.
# ---------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  log "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
log "uv $(uv --version)"

# ---------------------------------------------------------------------------
# 2. PostgreSQL 16 — a system dependency that is not in the base image.
# ---------------------------------------------------------------------------
if ! command -v pg_ctlcluster >/dev/null 2>&1; then
  log "Installing PostgreSQL 16"
  sudo apt-get update -qq
  sudo apt-get install -y -qq postgresql-16 postgresql-client-16
fi

# Default max_locks_per_transaction (64) is too low for pytest-xdist, which runs
# many workers that each build every table via syncdb (--nomigrations). Mirrors
# docker-compose.yml and scripts/setup_web.sh.
PG_CONF="/etc/postgresql/16/main/postgresql.conf"
if [ -f "$PG_CONF" ] && ! grep -q 'max_locks_per_transaction = 256' "$PG_CONF"; then
  log "Tuning PostgreSQL max_locks_per_transaction"
  echo "max_locks_per_transaction = 256" | sudo tee -a "$PG_CONF" >/dev/null
fi

# Bring PostgreSQL up so migrations can run (start.sh does this on every boot).
sudo pg_ctlcluster 16 main start 2>/dev/null || sudo service postgresql start 2>/dev/null || true
for _ in $(seq 1 30); do pg_isready -q && break; sleep 1; done
pg_isready -q || { echo "PostgreSQL failed to start" >&2; exit 1; }
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';" >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# 3. Python environment — uv creates .venv and installs exactly what uv.lock
#    pins (including the CPython 3.14 interpreter).
# ---------------------------------------------------------------------------
log "Syncing Python environment (uv sync --locked)"
UV_PROJECT_ENVIRONMENT=.venv uv sync --locked
# shellcheck disable=SC1091
source .venv/bin/activate
log "Python $(python --version)"

# ---------------------------------------------------------------------------
# 4. .env — random SECRET_KEY + superuser password. DB settings come from
#    .env.example (DB_NAME=postgres, user/password postgres on localhost:5432).
#    setupenv only fills in what is missing, so re-runs keep the existing keys.
# ---------------------------------------------------------------------------
log "Configuring .env"
manage setupenv

# ---------------------------------------------------------------------------
# 5. Database + migrations.
# ---------------------------------------------------------------------------
DB_NAME=$(grep '^DB_NAME=' .env | cut -d= -f2)
DB_NAME=${DB_NAME:-postgres}
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  log "Creating database '${DB_NAME}'"
  sudo -u postgres createdb "${DB_NAME}"
fi

# Migration ordering on a FRESH database. Two things go wrong with a plain
# `manage migrate` here:
#   * analytics.0002 performs the real ALTER on the core_event table, but the
#     migration plan schedules it BEFORE the core migration that physically
#     creates core_event -> "relation core_event does not exist".
#   * Migrating a single app first (to force core_event to exist) only pulls
#     auth.0001, whose auth_permission.name is varchar(50); the post_migrate
#     permission creation for long-named historical models then overflows it.
# Fully migrating auth first, then core (which creates core_event and pulls in
# analytics.0001 as a state-only dependency), then everything, avoids both.
# Each command is a no-op once its migrations are applied, so this is idempotent.
log "Running migrations"
manage migrate auth
manage migrate core
manage migrate

# ---------------------------------------------------------------------------
# 6. Frontend assets + static files.
# ---------------------------------------------------------------------------
log "Installing Node dependencies and building assets"
npm install
npm run build
manage collectstatic --noinput

log "Install complete"
