#!/usr/bin/env bash
# Wrapper so the pre-commit hook does not depend on python3 being on PATH.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/worktree.sh
source "${SCRIPT_DIR}/lib/worktree.sh"
PYTHON=$(worktree_python "$ROOT") || exit 1
cd "$ROOT"
exec "$PYTHON" scripts/check_raw_markup.py "$@"
