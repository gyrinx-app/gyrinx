#!/usr/bin/env bash
# Shared path validation for the Codex lifecycle scripts.

CODEX_SCRIPT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)

codex_error() {
  echo "ERROR: $*" >&2
  exit 1
}

# Require an existing repository root in the same Git repository as this script.
# Canonicalise paths so trailing slashes and symlinks use the normal DB hash.
codex_tree_root() {
  local path="$1" root common script_common
  root=$(cd "$path" && pwd -P) || return 1
  [ "$root" = "$(git -C "$root" rev-parse --show-toplevel)" ] || {
    echo "ERROR: Expected a Git worktree root: $path" >&2
    return 1
  }
  common=$(git -C "$root" rev-parse --path-format=absolute --git-common-dir)
  script_common=$(git -C "$CODEX_SCRIPT_ROOT" rev-parse --path-format=absolute --git-common-dir)
  [ "$common" = "$script_common" ] || {
    echo "ERROR: Worktree belongs to another repository: $path" >&2
    return 1
  }
  printf '%s\n' "$root"
}
