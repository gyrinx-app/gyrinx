#!/bin/bash
# Run the test suite against the local PostgreSQL database.
#
# Assumes PostgreSQL is running and the venv is active (the SessionStart
# hook handles both for Claude Code sessions; ./scripts/dev.sh handles them
# for interactive use).  CI invokes pytest directly — see
# .github/workflows/test.yaml.
#
# Usage:
#   ./scripts/test.sh                 # serial
#   ./scripts/test.sh --parallel      # pytest-xdist (-n auto)
#   ./scripts/test.sh <pytest args>   # passed through

set -e

PYTEST_ARGS=()
if [ "${1:-}" = "--parallel" ] || [ "${1:-}" = "-p" ]; then
    PYTEST_ARGS+=("-n" "auto")
    shift
fi

if [ $# -gt 0 ]; then
    PYTEST_ARGS+=("$@")
fi

exec pytest "${PYTEST_ARGS[@]}"
