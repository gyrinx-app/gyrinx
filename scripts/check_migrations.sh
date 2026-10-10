#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/worktree.sh
source "${SCRIPT_DIR}/lib/worktree.sh"
# shellcheck source=lib/untracked_migrations.sh
source "${SCRIPT_DIR}/lib/untracked_migrations.sh"

_restore_hidden_migrations() {
  local status=$?
  restore_untracked_migrations
  exit "$status"
}
trap _restore_hidden_migrations EXIT

cd "$ROOT"

# Call hide once. A second call forgets the directory the first move used.
_hide_untracked=0
if [[ "${PRE_COMMIT:-}" == "1" ]]; then
  _hide_untracked=1
fi
for _arg in "$@"; do
  if [[ "$_arg" == "--pre-commit" ]]; then
    _hide_untracked=1
  fi
done
if [[ "$_hide_untracked" == "1" ]]; then
  hide_untracked_migrations --pre-commit
fi

PYTHON=$(worktree_python "$ROOT") || exit 1
if ! "$PYTHON" scripts/manage.py makemigrations --check --dry-run --verbosity 0; then
    echo "Migrations are not up to date. Please run 'manage makemigrations' to create new migrations."
    exit 1
fi
