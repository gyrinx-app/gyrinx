#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "Usage: .codex/run.sh <command> [args ...]" >&2
  exit 2
fi

PROJECT_DIR=$(git rev-parse --show-toplevel)
VENV_ACTIVATE="${PROJECT_DIR}/.venv/bin/activate"
WORKTREE_LIB="${PROJECT_DIR}/scripts/lib/worktree.sh"

if [ ! -f "$VENV_ACTIVATE" ]; then
  echo "No worktree virtualenv found at ${PROJECT_DIR}/.venv." >&2
  echo "Run .codex/setup.sh before running project commands." >&2
  exit 1
fi

# The activation script includes the repository's per-worktree DB hook, which
# sets DB_NAME, DJANGO_PORT and DB_CONFIG for this checkout.
# shellcheck disable=SC1090
source "$VENV_ACTIVATE"

# Do not depend on the optional activation block installed by
# setup-local-postgres.sh. Older main-worktree venvs may not contain it.
# shellcheck disable=SC1090
source "$WORKTREE_LIB"
export DB_NAME
DB_NAME=$(worktree_db_name "$PROJECT_DIR")
export DJANGO_PORT
DJANGO_PORT=$(worktree_port "$PROJECT_DIR")
export DB_HOST=localhost
export DB_PORT=5432
export DB_CONFIG
DB_CONFIG=$(db_config_for_local)
export DJANGO_SETTINGS_MODULE=gyrinx.settings_dev

PG_BIN_DIR=$(homebrew_postgres_bin)
if [ -n "$PG_BIN_DIR" ]; then
  export PATH="${PG_BIN_DIR}:${PATH}"
fi

exec "$@"
