#!/bin/bash
set -euo pipefail

# =============================================================================
# Claude Code on the Web: Gyrinx Environment Setup
#
# This script is invoked by the SessionStart hook (see .claude/settings.json).
# It only runs in remote (web) environments and prepares the full development
# environment so that Claude Code can run tests, linters, and formatters.
# =============================================================================

# Only run in remote (Claude Code on the Web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  echo "Skipping web setup (not a remote environment)."
  exit 0
fi

echo "=== Claude Code on the Web: Gyrinx Environment Setup ==="

# ---------------------------------------------------------------------------
# 0. Fix sudo configuration ownership
# ---------------------------------------------------------------------------
# In some web environments, /etc/sudo.conf and /etc/sudoers end up owned by
# the container user instead of root, which breaks all sudo commands.  Since
# this script runs as root we can fix this before anything else.
for f in /etc/sudo.conf /etc/sudoers; do
  if [ -f "$f" ] && [ "$(stat -c '%u' "$f")" != "0" ]; then
    echo "Fixing ownership of $f ..."
    chown root:root "$f"
  fi
done
if [ -d /etc/sudoers.d ]; then
  if [ "$(stat -c '%u' /etc/sudoers.d)" != "0" ]; then
    echo "Fixing ownership of /etc/sudoers.d/ ..."
    chown -R root:root /etc/sudoers.d
  fi
fi

# ---------------------------------------------------------------------------
# 1. Install GitHub CLI
# ---------------------------------------------------------------------------
echo "--- [1/10] Installing GitHub CLI ---"
if ! command -v gh &>/dev/null; then
  # Install from a direct binary download rather than apt.
  # The web environment has limited network; apt-get update fails because
  # it tries to reach every configured apt source (PPAs, etc.).  Direct
  # download only needs github.com + objects.githubusercontent.com, both
  # on the allow-list.
  GH_VERSION="2.67.0"
  # Map kernel arch to the naming convention used by gh release tarballs.
  case "$(uname -m)" in
    x86_64)  GH_ARCH="amd64" ;;
    aarch64) GH_ARCH="arm64" ;;
    *)       GH_ARCH="$(uname -m)" ;;
  esac
  GH_TARBALL="gh_${GH_VERSION}_linux_${GH_ARCH}"
  curl -LsSf "https://github.com/cli/cli/releases/download/v${GH_VERSION}/${GH_TARBALL}.tar.gz" \
    -o /tmp/gh.tar.gz
  tar -xzf /tmp/gh.tar.gz -C /tmp
  sudo install /tmp/"${GH_TARBALL}"/bin/gh /usr/local/bin/gh
  rm -rf /tmp/gh.tar.gz /tmp/"${GH_TARBALL}"
  echo "gh installed: $(gh --version | head -1)"
else
  echo "gh already installed: $(gh --version | head -1)"
fi

# ---------------------------------------------------------------------------
# 2. Ensure the "claude-code-web" label exists on the repo
# ---------------------------------------------------------------------------
echo "--- [2/10] Ensuring 'claude-code-web' GitHub label exists ---"
if gh auth status &>/dev/null; then
  gh label create claude-code-web \
    --description "Issue is being worked on in a Claude Code for Web session" \
    --color "1d76db" \
    --force 2>/dev/null \
    && echo "Label 'claude-code-web' ensured." \
    || echo "Warning: could not create label (non-fatal)."
else
  echo "gh not authenticated — skipping label creation."
fi

# ---------------------------------------------------------------------------
# 3. Install uv
# ---------------------------------------------------------------------------
echo "--- [3/10] Installing uv ---"
# The image ships a uv, but pyproject.toml pins `[tool.uv] required-version`
# and `uv sync --locked` refuses an older one. An "install only if missing"
# check therefore left the image's uv 0.8.17 in place and aborted the whole
# script at the sync step (no .venv, no .env, no Postgres, no node_modules).
# Read the floor from pyproject.toml so the two never drift apart.
UV_MIN=$(sed -n 's/^required-version = ">=\([0-9.]*\)"/\1/p' pyproject.toml | head -1)
UV_MIN="${UV_MIN:-0.11.12}"
uv_satisfies_pin() {
  command -v uv &>/dev/null || return 1
  # `sort -V -C` succeeds when the lines are already in version order, i.e.
  # when the installed version is at least UV_MIN.
  printf '%s\n%s\n' "$UV_MIN" "$(uv --version | awk '{print $2}')" | sort -V -C
}
if ! uv_satisfies_pin; then
  echo "uv missing or older than ${UV_MIN} — installing the current release..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Venv doesn't exist yet, so $HOME/.local/bin goes first just to pick up uv.
  # The persisted PATH (below) puts the venv bin first once it's been created.
  export PATH="$HOME/.local/bin:$PATH"
  hash -r
fi
echo "uv: $(uv --version)"

# ---------------------------------------------------------------------------
# 4. Python virtual environment + project install
# ---------------------------------------------------------------------------
echo "--- [4/10] Setting up Python environment ---"
# `uv sync` creates .venv if needed and installs exactly what uv.lock pins.
# UV_PROJECT_ENVIRONMENT is pinned because the next line sources ./.venv — an
# inherited value would sync a different environment and leave this broken.
UV_PROJECT_ENVIRONMENT=.venv uv sync --locked
# shellcheck disable=SC1091
source .venv/bin/activate
echo "Python $(python --version) — packages installed"

# ---------------------------------------------------------------------------
# 5. Agent board
# ---------------------------------------------------------------------------
# The cloud environment installs the `board` CLI and sets BOARD_TOKEN. Its hooks
# run from .claude/settings.json via scripts/board_hook.sh and create and link
# this repo's board on the first prompt; `board init` here is idempotent and
# only makes `board who` work before that first prompt. Nothing fails without it.
echo "--- [5/10] Agent board ---"
if command -v board >/dev/null 2>&1 && [ -n "${BOARD_TOKEN:-}" ]; then
  board init 2>&1 | tail -1 || echo "board init failed (non-fatal)."
else
  echo "board CLI or BOARD_TOKEN missing — skipping."
fi

# ---------------------------------------------------------------------------
# 6. Environment configuration (.env)
# ---------------------------------------------------------------------------
echo "--- [6/10] Setting up .env ---"
manage setupenv

# ---------------------------------------------------------------------------
# 7. PostgreSQL
# ---------------------------------------------------------------------------
echo "--- [7/10] Setting up PostgreSQL ---"

# Fix SSL private key permissions.  In web environments the snakeoil key
# sometimes ends up with group/world access, which causes PostgreSQL to
# refuse to start with:
#   FATAL: private key file "..." has group or world access
SSL_KEY="/etc/ssl/private/ssl-cert-snakeoil.key"
if [ -f "$SSL_KEY" ]; then
  PERMS=$(stat -c '%a' "$SSL_KEY" 2>/dev/null || true)
  if [ -n "$PERMS" ] && [ "$PERMS" != "600" ] && [ "$PERMS" != "640" ]; then
    echo "Fixing SSL key permissions ($PERMS -> 600)..."
    sudo chmod 600 "$SSL_KEY"
  fi
fi

# Tune PostgreSQL for parallel test workloads.  The default
# max_locks_per_transaction (64) is too low when pytest-xdist spins up many
# workers that each create all tables via syncdb (--nomigrations).
PG_CONF="/etc/postgresql/16/main/postgresql.conf"
if [ -f "$PG_CONF" ]; then
  if ! grep -q 'max_locks_per_transaction = 256' "$PG_CONF" 2>/dev/null; then
    echo "Tuning PostgreSQL max_locks_per_transaction..."
    echo "max_locks_per_transaction = 256" | sudo tee -a "$PG_CONF" >/dev/null
    # Restart PostgreSQL if it's already running so the config change takes effect
    if pg_isready -q 2>/dev/null; then
      echo "Restarting PostgreSQL to apply config..."
      sudo pg_ctlcluster 16 main restart 2>/dev/null \
        || sudo service postgresql restart 2>/dev/null \
        || true
    fi
  fi
fi

# Start PostgreSQL if not already running
if ! pg_isready -q 2>/dev/null; then
  echo "Starting PostgreSQL..."
  if ! sudo pg_ctlcluster 16 main start 2>&1; then
    echo "pg_ctlcluster failed, trying service..."
    if ! sudo service postgresql start 2>&1; then
      echo "ERROR: Failed to start PostgreSQL."
      exit 1
    fi
  fi
fi

# Wait for readiness
PG_READY=false
for i in $(seq 1 30); do
  if pg_isready -q 2>/dev/null; then
    echo "PostgreSQL is ready."
    PG_READY=true
    break
  fi
  sleep 1
done
if [ "$PG_READY" != "true" ]; then
  echo "ERROR: PostgreSQL did not become ready in 30 s."
  exit 1
fi

# Set the postgres user password so TCP connections with password auth work
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';" 2>/dev/null || true

# Read the DB_NAME from .env (falls back to the default used by settings.py)
DB_NAME=$(grep '^DB_NAME=' .env 2>/dev/null | cut -d'=' -f2 || echo "gyrinx")
DB_NAME="${DB_NAME:-gyrinx}"

# Create the database if it doesn't already exist
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" 2>/dev/null | grep -q 1; then
  echo "Creating database '${DB_NAME}'..."
  sudo -u postgres createdb "${DB_NAME}" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 8. Database migrations
# ---------------------------------------------------------------------------
echo "--- [8/10] Running database migrations ---"
manage migrate

# ---------------------------------------------------------------------------
# 9. Node.js dependencies + pre-commit hooks
# ---------------------------------------------------------------------------
echo "--- [9/10] Installing Node.js deps and pre-commit hooks ---"
npm install
pre-commit install

# ---------------------------------------------------------------------------
# 10. Build frontend assets + collect static files
# ---------------------------------------------------------------------------
echo "--- [10/10] Building frontend and collecting static files ---"
npm run build
manage collectstatic --noinput

# ---------------------------------------------------------------------------
# NOTE: Virtualenv activation for subsequent commands is handled by the
# separate activate_venv_hook.sh SessionStart hook (see .claude/settings.json).
# That hook runs independently so venv activation succeeds even if this
# script fails partway through.
# ---------------------------------------------------------------------------

echo "=== Setup complete! ==="
