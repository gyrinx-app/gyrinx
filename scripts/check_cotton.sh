#!/usr/bin/env bash
# Check Cotton attributes and error bindings for unsafe or broken HTML.
# Run from the repository root; pre-commit and CI also run this check.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/worktree.sh
source "${SCRIPT_DIR}/lib/worktree.sh"
PYTHON=$(worktree_python "$ROOT") || exit 1
cd "$ROOT"
exec "$PYTHON" scripts/check_cotton.py "$@"
