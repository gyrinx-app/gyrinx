#!/bin/bash
# Run the test suite against the local PostgreSQL database.
#
# Assumes PostgreSQL is running and the venv is active (the SessionStart
# hook handles both for Claude Code sessions; ./scripts/dev.sh handles them
# for interactive use).  CI invokes pytest directly — see
# .github/workflows/test.yaml.
#
# pyproject.toml already sets `-n auto --nomigrations`, so the bare
# invocation runs in parallel by default.  Pass `-n 0` to force serial.
#
# Usage:
#   ./scripts/test.sh                 # parallel (via addopts -n auto)
#   ./scripts/test.sh -n 0            # serial
#   ./scripts/test.sh <pytest args>   # passed through to pytest

set -e

exec pytest "$@"
