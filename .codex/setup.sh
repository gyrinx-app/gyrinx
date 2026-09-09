#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=worktree.sh
source "$SCRIPT_DIR/worktree.sh"

[ "$#" -eq 0 ] || codex_error "Usage: .codex/setup.sh"
PROJECT_DIR=$(codex_tree_root "${CODEX_WORKTREE_PATH:-$(git rev-parse --show-toplevel)}")
cd "$PROJECT_DIR"

# A new worktree can be based on another child worktree, not just main.
# Keep any existing local configuration when setup is rerun.
if [ -n "${CODEX_SOURCE_TREE_PATH:-}" ]; then
  SOURCE_DIR=$(codex_tree_root "$CODEX_SOURCE_TREE_PATH")
else
  source "$PROJECT_DIR/scripts/lib/worktree.sh"
  SOURCE_DIR=$(_main_worktree)
fi

# These directories must belong to this worktree: dependency installers can
# otherwise mutate a source checkout through a symlink.
for path in .env .venv node_modules; do
  [ ! -L "$PROJECT_DIR/$path" ] || codex_error "Remove the shared symlink before setup: $PROJECT_DIR/$path"
done
if [ ! -e "$PROJECT_DIR/.env" ] && [ -f "$SOURCE_DIR/.env" ]; then
  (umask 077; cp "$SOURCE_DIR/.env" "$PROJECT_DIR/.env")
  chmod 600 "$PROJECT_DIR/.env"
  echo "Copied .env from source workspace."
fi

# Provisions dependencies, forks the worktree database, migrates and builds CSS.
# No background server is left running by the setup hook.
exec ./scripts/dev.sh --no-watch --setup-only
