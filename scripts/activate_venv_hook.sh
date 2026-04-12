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
  MAIN_WT=$(git -C "${CLAUDE_PROJECT_DIR:-.}" worktree list 2>/dev/null | head -1 | awk '{print $1}')
  if [ -n "$MAIN_WT" ] && [ -d "${MAIN_WT}/.venv" ]; then
    VENV_PATH="${MAIN_WT}/.venv"
  else
    exit 0
  fi
fi

# Persist environment so every subsequent Bash tool call has the venv active.
{
  echo "PATH=/opt/homebrew/opt/postgresql@16/bin:${VENV_PATH}/bin:$HOME/.local/bin:$PATH"
  echo "VIRTUAL_ENV=${VENV_PATH}"
  echo "DJANGO_SETTINGS_MODULE=gyrinx.settings_dev"
} >> "$CLAUDE_ENV_FILE"

# Set per-worktree DB_NAME and DJANGO_PORT so manage/pytest target the right DB.
WORKTREE_LIB="${CLAUDE_PROJECT_DIR:-.}/scripts/lib/worktree.sh"
if [ -f "$WORKTREE_LIB" ]; then
  source "$WORKTREE_LIB"
  WT_ROOT=$(_worktree_root)
  if [ -n "$WT_ROOT" ]; then
    {
      echo "DB_NAME=$(worktree_db_name "$WT_ROOT")"
      echo "DJANGO_PORT=$(worktree_port "$WT_ROOT")"
      echo "DB_HOST=localhost"
      echo "DB_PORT=5432"
      echo "DB_CONFIG=$(db_config_for_local)"
    } >> "$CLAUDE_ENV_FILE"
  fi
fi
