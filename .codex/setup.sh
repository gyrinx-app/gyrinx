#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR=$(git rev-parse --show-toplevel)
cd "$PROJECT_DIR"

# Reuse the normal development bootstrap. In setup-only mode it provisions the
# worktree venv and frontend dependencies, forks the per-worktree database,
# migrates it, and builds CSS without leaving a server running.
exec ./scripts/dev.sh --no-watch --setup-only
