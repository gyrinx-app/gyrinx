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
# 1. Install GitHub CLI
# ---------------------------------------------------------------------------
echo "--- [1/8] Installing GitHub CLI ---"
if ! command -v gh &>/dev/null; then
  # Install from a direct binary download rather than apt.
  # The web environment has limited network; apt-get update fails because
  # it tries to reach every configured apt source (PPAs, etc.).  Direct
  # download only needs github.com + objects.githubusercontent.com, both
  # on the allow-list.
  GH_VERSION="2.67.0"
  curl -LsSf "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
    -o /tmp/gh.tar.gz
  tar -xzf /tmp/gh.tar.gz -C /tmp
  sudo install /tmp/"gh_${GH_VERSION}_linux_amd64"/bin/gh /usr/local/bin/gh
  rm -rf /tmp/gh.tar.gz /tmp/"gh_${GH_VERSION}_linux_amd64"
  echo "gh installed: $(gh --version | head -1)"
else
  echo "gh already installed: $(gh --version | head -1)"
fi

# ---------------------------------------------------------------------------
# 2. Install uv
# ---------------------------------------------------------------------------
echo "--- [2/8] Installing uv ---"
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "uv: $(uv --version)"

# ---------------------------------------------------------------------------
# 3. Python virtual environment + project install
# ---------------------------------------------------------------------------
echo "--- [3/8] Setting up Python environment ---"
uv venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install --editable .
echo "Python $(python --version) — packages installed"

# ---------------------------------------------------------------------------
# 4. Environment configuration (.env)
# ---------------------------------------------------------------------------
echo "--- [4/8] Setting up .env ---"
manage setupenv

# ---------------------------------------------------------------------------
# 5. PostgreSQL
# ---------------------------------------------------------------------------
echo "--- [5/8] Setting up PostgreSQL ---"

# Start PostgreSQL if not already running
if ! pg_isready -q 2>/dev/null; then
  echo "Starting PostgreSQL..."
  sudo pg_ctlcluster 16 main start 2>/dev/null \
    || sudo service postgresql start 2>/dev/null \
    || true
fi

# Wait for readiness
for i in $(seq 1 30); do
  if pg_isready -q 2>/dev/null; then
    echo "PostgreSQL is ready."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "WARNING: PostgreSQL did not become ready in 30 s."
  fi
  sleep 1
done

# Set the postgres user password so TCP connections with password auth work
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 6. Database migrations
# ---------------------------------------------------------------------------
echo "--- [6/8] Running database migrations ---"
manage migrate

# ---------------------------------------------------------------------------
# 7. Node.js dependencies + pre-commit hooks
# ---------------------------------------------------------------------------
echo "--- [7/8] Installing Node.js deps and pre-commit hooks ---"
npm install
pre-commit install

# ---------------------------------------------------------------------------
# 8. Build frontend assets + collect static files
# ---------------------------------------------------------------------------
echo "--- [8/8] Building frontend and collecting static files ---"
npm run build
manage collectstatic --noinput

# ---------------------------------------------------------------------------
# Persist environment variables for all subsequent Claude Code commands
# ---------------------------------------------------------------------------
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "--- Persisting environment variables ---"
  VENV_PATH="${CLAUDE_PROJECT_DIR:-.}/.venv"
  {
    echo "PATH=$HOME/.local/bin:${VENV_PATH}/bin:$PATH"
    echo "VIRTUAL_ENV=${VENV_PATH}"
    echo "DJANGO_SETTINGS_MODULE=gyrinx.settings_dev"
  } >> "$CLAUDE_ENV_FILE"
fi

echo "=== Setup complete! ==="
