#!/bin/bash
#
# Refuse a branch that adds more than one migration leaf to an app.
#
# Several leaves per app are allowed on main (see gyrinx/migration_graph.py):
# branches merge without renaming or repointing and the next generated
# migration joins them. A single branch adding two leaves means a migration
# was written by hand on a tree whose other leaf it ignored.
#
# Compares against origin/main unless MIGRATION_BASE says otherwise. Requires
# Django to be importable (run inside the virtualenv or CI after `uv sync`).

set -euo pipefail

python scripts/manage.py check_migration_conflicts --base "${MIGRATION_BASE:-origin/main}"
