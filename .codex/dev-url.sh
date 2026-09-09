#!/usr/bin/env bash
# Print or open the dev URL for the checkout running this toolbar action.

set -euo pipefail

case "${1:-}" in
  ""|--open) ;;
  *) echo "Usage: .codex/dev-url.sh [--open]" >&2; exit 2 ;;
esac
[ "$#" -le 1 ] || { echo "Usage: .codex/dev-url.sh [--open]" >&2; exit 2; }
PROJECT_DIR=$(git rev-parse --show-toplevel)
source "$PROJECT_DIR/scripts/lib/worktree.sh"
URL="http://localhost:$(worktree_port "$PROJECT_DIR")/"
printf '%s\n' "$URL"

if [ "${1:-}" = --open ]; then
  case "$(uname -s)" in
    Darwin) exec open "$URL" ;;
    Linux) exec xdg-open "$URL" ;;
    *) echo "Open the URL above in your browser." >&2; exit 1 ;;
  esac
fi
