#!/usr/bin/env bash
# Clean up orphaned worktree databases.
#
# Lists all gyrinx_wt_* databases and drops any whose worktree no longer exists.
#
# Requires bash 4+ for associative arrays.  macOS ships /bin/bash 3.2, so the
# shebang uses /usr/bin/env bash to pick up the Homebrew bash on PATH.
#
# Usage:
#   ./scripts/cleanup-worktree-dbs.sh           # Dry run (list orphans)
#   ./scripts/cleanup-worktree-dbs.sh --force   # Actually drop orphans

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: This script requires bash 4+ (you have $BASH_VERSION)." >&2
  echo "Install via: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/worktree.sh
source "$SCRIPT_DIR/lib/worktree.sh"

PG_BIN_DIR=$(homebrew_postgres_bin)
if [ -n "$PG_BIN_DIR" ]; then
  export PATH="$PG_BIN_DIR:$PATH"
fi

FORCE=false
[ "${1:-}" = "--force" ] && FORCE=true

# ---------------------------------------------------------------------------
# Build set of expected DB names from active worktrees
# ---------------------------------------------------------------------------
declare -A EXPECTED_DBS
while IFS= read -r line; do
  wt_path=$(echo "$line" | awk '{print $1}')
  db=$(worktree_db_name "$wt_path")
  EXPECTED_DBS["$db"]=1
done < <(git worktree list)

# ---------------------------------------------------------------------------
# Find all gyrinx_wt_* databases
# ---------------------------------------------------------------------------
ORPHANS=()
while IFS= read -r db; do
  db=$(echo "$db" | xargs)  # trim whitespace
  [ -z "$db" ] && continue
  if [ -z "${EXPECTED_DBS[$db]+x}" ]; then
    ORPHANS+=("$db")
  fi
done < <(psql -d postgres -tAc "SELECT datname FROM pg_database WHERE datname LIKE 'gyrinx_wt_%' ORDER BY datname;")

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
if [ ${#ORPHANS[@]} -eq 0 ]; then
  echo "No orphaned worktree databases found."
  exit 0
fi

echo "Found ${#ORPHANS[@]} orphaned database(s):"
for db in "${ORPHANS[@]}"; do
  size=$(psql -d postgres -tAc "SELECT pg_size_pretty(pg_database_size('$db'));")
  echo "  - $db ($size)"
done

if [ "$FORCE" = false ]; then
  echo
  echo "Run with --force to drop these databases."
  exit 0
fi

# ---------------------------------------------------------------------------
# Drop orphans
# ---------------------------------------------------------------------------
echo
for db in "${ORPHANS[@]}"; do
  echo "Dropping $db..."
  # Terminate any lingering connections
  psql -d postgres -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = '$db' AND pid <> pg_backend_pid();
  " >/dev/null 2>&1 || true
  dropdb "$db"
done
echo "Done. Dropped ${#ORPHANS[@]} database(s)."
