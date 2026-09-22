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

# Run git with a per-command HTTPS rewrite for git@github.com: URLs.
# Codex sandboxes often have `gh` authenticated but no SSH agent key, so a
# stored git@github.com: remote fails with "publickey". Passing -c keeps the
# rewrite off the shared worktree config — `git config --local` in a linked
# worktree writes the common config and would change the human's main checkout.
# Apply the rewrite only when `gh` is on PATH, origin is still SSH, and no
# existing insteadOf has already turned it into HTTPS. Does not exec, so
# callers can inspect the exit status.
codex_github_https_git() {
  if ! command -v gh >/dev/null 2>&1; then
    git "$@"
    return $?
  fi
  local origin effective
  origin=$(git remote get-url origin 2>/dev/null || true)
  case "$origin" in
    git@github.com:*|ssh://git@github.com/*|ssh://git@github.com:*) ;;
    *)
      git "$@"
      return $?
      ;;
  esac
  effective=$(git ls-remote --get-url origin 2>/dev/null || true)
  case "$effective" in
    git@github.com:*|ssh://git@github.com/*|ssh://git@github.com:*)
      git \
        -c "url.https://github.com/.insteadOf=git@github.com:" \
        -c "credential.https://github.com.helper=!gh auth git-credential" \
        "$@"
      return $?
      ;;
  esac
  git "$@"
}
