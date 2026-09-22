#!/usr/bin/env bash
#
# Refuse a branch that adds more than one migration leaf to an app.
#
# Several leaves per app are allowed on main (see gyrinx/migration_graph.py):
# branches merge without renaming or repointing and the next generated
# migration joins them. A single branch adding two leaves means a migration
# was written by hand on a tree whose other leaf it ignored.
#
# Compares against origin/main unless MIGRATION_BASE says otherwise. Uses the
# worktree .venv when present so a plain git commit can run this hook.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/worktree.sh
source "${SCRIPT_DIR}/lib/worktree.sh"

cd "$ROOT"
PYTHON=$(worktree_python "$ROOT") || exit 1
"$PYTHON" scripts/manage.py check_migration_conflicts --base "${MIGRATION_BASE:-origin/main}"
