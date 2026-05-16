#!/usr/bin/env bash
# Clean up orphaned worktree databases and pytest test databases.
#
# Default: lists worktree databases (gyrinx_wt_*) whose worktree no longer
# exists, plus any pytest test databases (test_gyrinx_*) attached to them.
# With --include-tests, also lists test databases for *active* worktrees (and
# for gyrinx_main) — pytest will recreate them on next run.
#
# Requires bash 4+ for associative arrays.  macOS ships /bin/bash 3.2, so the
# shebang uses /usr/bin/env bash to pick up the Homebrew bash on PATH.
#
# Usage:
#   ./scripts/cleanup-worktree-dbs.sh                    # Dry run
#   ./scripts/cleanup-worktree-dbs.sh --force            # Drop orphans
#   ./scripts/cleanup-worktree-dbs.sh --include-tests    # Dry run + active test DBs
#   ./scripts/cleanup-worktree-dbs.sh --include-tests --force

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
INCLUDE_TESTS=false
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
    --include-tests) INCLUDE_TESTS=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Build set of expected DB names from active worktrees
# ---------------------------------------------------------------------------
declare -A EXPECTED_DBS
# gyrinx_main is the template, always expected.
EXPECTED_DBS["gyrinx_main"]=1
# Use --porcelain so paths containing spaces aren't truncated by awk.
while IFS= read -r wt_path; do
  [ -z "$wt_path" ] && continue
  db=$(worktree_db_name "$wt_path")
  EXPECTED_DBS["$db"]=1
done < <(git worktree list --porcelain | sed -n 's/^worktree //p')

# ---------------------------------------------------------------------------
# Collect orphaned worktree DBs and orphaned/test DBs
# ---------------------------------------------------------------------------
ORPHAN_WORKTREES=()
ORPHAN_TESTS=()
ACTIVE_TESTS=()

while IFS= read -r db; do
  db=$(echo "$db" | xargs)  # trim whitespace
  [ -z "$db" ] && continue

  # Worktree DBs: gyrinx_wt_<8hex>
  if [[ "$db" =~ ^gyrinx_wt_[0-9a-f]{8}$ ]]; then
    if [ -z "${EXPECTED_DBS[$db]+x}" ]; then
      ORPHAN_WORKTREES+=("$db")
    fi
    continue
  fi

  # pytest test DBs: test_gyrinx_main[_gwN] or test_gyrinx_wt_<8hex>[_gwN]
  if [[ "$db" =~ ^test_(gyrinx_main|gyrinx_wt_[0-9a-f]{8})(_gw[0-9]+)?$ ]]; then
    base="${BASH_REMATCH[1]}"
    if [ -z "${EXPECTED_DBS[$base]+x}" ]; then
      ORPHAN_TESTS+=("$db")
    else
      ACTIVE_TESTS+=("$db")
    fi
  fi
done < <(psql -d postgres -tAc "SELECT datname FROM pg_database WHERE datname LIKE 'gyrinx_%' OR datname LIKE 'test_gyrinx_%' ORDER BY datname;")

# ---------------------------------------------------------------------------
# Build the kill list (orphans always; active tests only with --include-tests)
# ---------------------------------------------------------------------------
TO_DROP=("${ORPHAN_WORKTREES[@]}" "${ORPHAN_TESTS[@]}")
if [ "$INCLUDE_TESTS" = true ]; then
  TO_DROP+=("${ACTIVE_TESTS[@]}")
fi

# ---------------------------------------------------------------------------
# Informational: report worktree .venv sizes
# ---------------------------------------------------------------------------
# Each child worktree has its own .venv (#1772).  We don't reap orphan .venvs
# — a venv lives inside its worktree directory, so `git worktree remove` (or
# rm -rf) takes it down with the worktree.  Surface the sizes so contributors
# can eyeball disk usage.
report_worktree_venvs() {
  local any=0
  while IFS= read -r wt_path; do
    [ -z "$wt_path" ] && continue
    if [ -d "$wt_path/.venv" ]; then
      if [ "$any" = 0 ]; then
        echo
        echo "Worktree .venv sizes:"
        any=1
      fi
      local size label
      # Best-effort: `du` can fail (race on dir removal, unreadable subtrees).
      # Don't let an informational lookup crash the script under `set -euo
      # pipefail` — fall back to "?" instead.
      size=$(du -sh "$wt_path/.venv" 2>/dev/null | awk '{print $1}' || echo "?")
      label=$(worktree_label "$wt_path")
      echo "  - ${label} (${wt_path}/.venv): ${size}"
    fi
  done < <(git worktree list --porcelain | sed -n 's/^worktree //p')
}

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
if [ ${#TO_DROP[@]} -eq 0 ]; then
  echo "No databases to clean up."
  report_worktree_venvs
  exit 0
fi

total_bytes=0
echo "Will drop ${#TO_DROP[@]} database(s):"
for db in "${TO_DROP[@]}"; do
  bytes=$(psql -d postgres -tAc "SELECT pg_database_size('$db');" 2>/dev/null || echo 0)
  size=$(psql -d postgres -tAc "SELECT pg_size_pretty(pg_database_size('$db'));" 2>/dev/null || echo "?")
  echo "  - $db ($size)"
  total_bytes=$((total_bytes + bytes))
done
total_pretty=$(psql -d postgres -tAc "SELECT pg_size_pretty($total_bytes::bigint);")
echo "Total: $total_pretty"

if [ "$INCLUDE_TESTS" = false ] && [ ${#ACTIVE_TESTS[@]} -gt 0 ]; then
  echo
  echo "(${#ACTIVE_TESTS[@]} test DB(s) for active worktrees not shown — pass --include-tests to clean them too.)"
fi

if [ "$FORCE" = false ]; then
  echo
  echo "Run with --force to drop these databases."
  report_worktree_venvs
  exit 0
fi

# ---------------------------------------------------------------------------
# Drop
# ---------------------------------------------------------------------------
echo
for db in "${TO_DROP[@]}"; do
  echo "Dropping $db..."
  psql -d postgres -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = '$db' AND pid <> pg_backend_pid();
  " >/dev/null 2>&1 || true
  dropdb "$db"
done
echo "Done. Dropped ${#TO_DROP[@]} database(s) ($total_pretty)."
report_worktree_venvs
