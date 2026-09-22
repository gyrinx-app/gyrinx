#!/usr/bin/env bash
# Push the current branch over HTTPS with `gh auth` when GitHub SSH is rejected.
# Does not change the stored remote. Usage: .codex/push.sh [git-push-args...]
# Example: .codex/push.sh -u origin HEAD

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=worktree.sh
source "$SCRIPT_DIR/worktree.sh"

codex_github_https_git push "$@"
