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

# ---------------------------------------------------------------------------
# 7. Read-only production database access.
#
#    A cloud agent authenticates to Google Cloud with a five-minute token that
#    scripts/cursor/mint-gcp-token.sh obtains from the local Cursor socket. The
#    token is federated into a service account that can only SELECT, so there is
#    no service account key anywhere on the machine.
#
#    Only the TOOLS are installed here. The credential config itself is written
#    on every boot by .cursor/start.sh, because it arrives in an environment
#    variable and a build snapshot must not capture it.
# ---------------------------------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  log "Installing jq"
  sudo apt-get update -qq
  sudo apt-get install -y -qq jq
fi

# Version and checksums are pinned rather than resolved at build time: the
# GitHub releases API is rate limited for unauthenticated callers, so resolving
# "latest" here would make builds fail unpredictably. Google publishes no
# checksum sidecar, so these were computed from the pinned release.
CSP_VERSION="v2.25.3"
CSP_BIN="/usr/local/bin/cloud-sql-proxy"
if ! "$CSP_BIN" --version 2>/dev/null | grep -q "${CSP_VERSION#v}"; then
  case "$(uname -m)" in
    x86_64)
      CSP_ARCH="amd64"
      CSP_SHA="f0584d79e877a8a46300fe2513840972c44e704c15dc3da6a49d5408f7d6f233"
      ;;
    aarch64)
      CSP_ARCH="arm64"
      CSP_SHA="9ffbf512ee24dbeca527eb12fc43d7a322724afccf369d7c172995fca35444d9"
      ;;
    *)
      echo "Unsupported architecture $(uname -m) for cloud-sql-proxy" >&2
      exit 1
      ;;
  esac
  log "Installing cloud-sql-proxy ${CSP_VERSION} (${CSP_ARCH})"
  CSP_TMP=$(mktemp)
  curl -sfLo "$CSP_TMP" \
    "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/${CSP_VERSION}/cloud-sql-proxy.linux.${CSP_ARCH}"
  echo "${CSP_SHA}  ${CSP_TMP}" | sha256sum -c - >/dev/null
  sudo install -m 0755 "$CSP_TMP" "$CSP_BIN"
  rm -f "$CSP_TMP"
fi
log "$("$CSP_BIN" --version 2>/dev/null | head -1)"

log "Install complete"
