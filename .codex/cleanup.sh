#!/usr/bin/env bash
# Run before Codex removes the worktree. Codex owns file/branch deletion.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=worktree.sh
source "$SCRIPT_DIR/worktree.sh"

DRY_RUN=false
case "${1:-}" in
  --dry-run) DRY_RUN=true; shift ;;
  "") ;;
  *) codex_error "Usage: .codex/cleanup.sh [--dry-run]" ;;
esac
[ "$#" -eq 0 ] || codex_error "Usage: .codex/cleanup.sh [--dry-run]"
PROJECT_DIR=$(codex_tree_root "${CODEX_WORKTREE_PATH:-$(git rev-parse --show-toplevel)}")
cd "$PROJECT_DIR"
source "$PROJECT_DIR/scripts/lib/worktree.sh"

DB_NAME=$(worktree_db_name "$PROJECT_DIR")
[[ "$DB_NAME" =~ ^gyrinx_wt_[0-9a-f]{8}$ ]] || codex_error "Cannot clean up the main worktree database."
PG_BIN_DIR=$(homebrew_postgres_bin)
if [ -n "$PG_BIN_DIR" ]; then
  export PATH="$PG_BIN_DIR:$PATH"
fi

# Use the local cluster, regardless of inherited production/test DB variables.
# Explicit arguments also override a PG service's connection defaults.
DB_HOST="${GYRINX_DB_HOST:-localhost}"
case "$DB_HOST" in
  localhost|127.0.0.1|/tmp|/private/tmp) ;;
  *) codex_error "Cleanup requires a local PostgreSQL host or socket directory." ;;
esac
PG_ARGS=(--host="$DB_HOST" --port=5432 --username="$(whoami)" --no-password)
DB_PATTERN="^(${DB_NAME}|test_${DB_NAME}(_gw[0-9]+)?)$"
# Capture first: a failed query must fail cleanup, not look like an empty list.
DATABASES=$(psql "${PG_ARGS[@]}" --dbname=postgres -X -v ON_ERROR_STOP=1 -Atc \
  "SELECT datname FROM pg_database WHERE datname ~ '$DB_PATTERN' ORDER BY datname;")

if [ -z "$DATABASES" ]; then
  echo "No databases to remove for $PROJECT_DIR."
  exit 0
fi

while IFS= read -r db; do
  [[ "$db" =~ $DB_PATTERN ]] || codex_error "Unexpected database name: $db"
  if [ "$DRY_RUN" = true ]; then
    echo "Would drop database: $db"
  else
    echo "Dropping database: $db"
    # No --force: fail if a dev server or test run still has connections.
    if ! dropdb "${PG_ARGS[@]}" --maintenance-db=postgres --if-exists "$db"; then
      codex_error "Could not drop $db. Stop this worktree's dev server and tests, then retry."
    fi
  fi
done <<< "$DATABASES"
