#!/bin/bash
# SessionStart hook: persist virtualenv activation for all Claude Code commands.
#
# This ensures every Bash tool invocation in the session has the project venv
# active without manual `. .venv/bin/activate` prefixes.  It runs independently
# of the heavier setup_web.sh so that venv activation succeeds even when other
# setup steps fail.
#
# Works in both local and remote (Claude Code on the Web) environments.
# See .claude/settings.json for hook registration.

set -euo pipefail

# CLAUDE_ENV_FILE is only available inside SessionStart hooks.  Variables
# written to it are injected into every subsequent Bash tool invocation.
if [ -z "${CLAUDE_ENV_FILE:-}" ]; then
  exit 0
fi

VENV_PATH="${CLAUDE_PROJECT_DIR:-.}/.venv"

# If no venv in current worktree, try the main worktree
if [ ! -d "$VENV_PATH" ]; then
  MAIN_WT=$(git -C "${CLAUDE_PROJECT_DIR:-.}" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p' | head -1)
  if [ -n "$MAIN_WT" ] && [ -d "${MAIN_WT}/.venv" ]; then
    VENV_PATH="${MAIN_WT}/.venv"
  else
    exit 0
  fi
fi

# Source the worktree library early so we can resolve the Postgres bin dir
# and (further down) per-worktree DB identity.
WORKTREE_LIB="${CLAUDE_PROJECT_DIR:-.}/scripts/lib/worktree.sh"
if [ -f "$WORKTREE_LIB" ]; then
  # shellcheck source=lib/worktree.sh
  source "$WORKTREE_LIB"
fi

# Resolve the Homebrew Postgres bin dir (Apple Silicon or Intel).  May be
# empty on systems without Postgres 16 installed — in that case we just
# omit it from PATH.
PG_BIN_DIR=""
if command -v homebrew_postgres_bin >/dev/null 2>&1; then
  PG_BIN_DIR=$(homebrew_postgres_bin)
fi

# Persist environment so every subsequent Bash tool call has the venv active.
# Use `export` so values propagate to child processes (pytest, manage, etc.),
# not just to the bash that sources this file.  Without `export`, the harness
# would set these as shell vars but `pytest` would see settings.py defaults
# (user=postgres, DB=gyrinx) and fail.
{
  if [ -n "$PG_BIN_DIR" ]; then
    echo "export PATH=\"${PG_BIN_DIR}:${VENV_PATH}/bin:$HOME/.local/bin:$PATH\""
  else
    echo "export PATH=\"${VENV_PATH}/bin:$HOME/.local/bin:$PATH\""
  fi
  echo "export VIRTUAL_ENV=\"${VENV_PATH}\""
  echo "export DJANGO_SETTINGS_MODULE=gyrinx.settings_dev"
} >> "$CLAUDE_ENV_FILE"

# Set per-worktree DB_NAME and DJANGO_PORT so manage/pytest target the right DB.
# The worktree_* helpers rely on `git` running inside the worktree, so cd
# into CLAUDE_PROJECT_DIR first — the SessionStart hook isn't guaranteed
# to inherit that as its cwd.
if command -v worktree_db_name >/dev/null 2>&1; then
  (
    cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
    WT_ROOT=$(_worktree_root)
    if [ -n "$WT_ROOT" ]; then
      # DB_CONFIG is JSON containing `{`, `}`, `"` — wrap in single quotes
      # so it survives shell sourcing (the harness re-sources CLAUDE_ENV_FILE
      # before every Bash invocation; an unquoted value would trip the parser).
      {
        echo "export DB_NAME=$(worktree_db_name "$WT_ROOT")"
        echo "export DJANGO_PORT=$(worktree_port "$WT_ROOT")"
        echo "export DB_HOST=localhost"
        echo "export DB_PORT=5432"
        echo "export DB_CONFIG='$(db_config_for_local)'"
      } >> "$CLAUDE_ENV_FILE"
    fi
  )
fi
