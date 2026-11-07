#!/usr/bin/env bash
# Rewrite package-lock.json with npm 11 after a package.json overrides change.
#
# npm 10 can leave an already installed nested dependency in place, so the
# lockfile no longer matches the override. npm 11 rewrites the lockfile from
# package.json. --check only runs npm ls and leaves the lockfile untouched.
#
#   ./scripts/update_package_lock.sh
#   ./scripts/update_package_lock.sh --check
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

check=0
dry_run=0
for arg in "$@"; do
  case "$arg" in
    --check) check=1 ;;
    --dry-run) dry_run=1 ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: ./scripts/update_package_lock.sh [--check] [--dry-run]" >&2
      exit 2
      ;;
  esac
done

npm_major=""
if npm_version="$(npm --version 2>/dev/null)"; then
  npm_major="${npm_version%%.*}"
fi

# npm ls on npm 10 already reports an override the lockfile missed. Rewriting
# the lockfile needs npm 11, including when this machine has no npm at all.
if [[ "$check" == "1" && "$npm_major" =~ ^[0-9]+$ ]]; then
  npm_cmd=(npm)
elif [[ "$npm_major" =~ ^[0-9]+$ ]] && ((npm_major >= 11)); then
  npm_cmd=(npm)
else
  npm_cmd=(npx --yes npm@11)
fi

print_cmd() {
  printf '%q' "$1"
  shift
  for arg in "$@"; do
    printf ' %q' "$arg"
  done
  printf '\n'
}

cd "$ROOT"

if [[ "$check" == "1" ]]; then
  if [[ "$dry_run" == "1" ]]; then
    print_cmd "${npm_cmd[@]}" ls --package-lock-only
    exit 0
  fi
  if ! "${npm_cmd[@]}" ls --package-lock-only; then
    echo "package-lock.json does not satisfy package.json overrides." >&2
    echo "npm 10 can leave a nested dependency in place after an override change." >&2
    echo "Regenerate with ./scripts/update_package_lock.sh and review the lockfile diff." >&2
    exit 1
  fi
  exit 0
fi

if [[ "$dry_run" == "1" ]]; then
  print_cmd "${npm_cmd[@]}" install --package-lock-only --ignore-scripts --no-audit --no-fund
  print_cmd "${npm_cmd[@]}" ls --package-lock-only
  exit 0
fi

"${npm_cmd[@]}" install --package-lock-only --ignore-scripts --no-audit --no-fund
"${npm_cmd[@]}" ls --package-lock-only
