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

if [ ! -d "$VENV_PATH" ]; then
  exit 0
fi

# Persist environment so every subsequent Bash tool call has the venv active.
{
  echo "PATH=${VENV_PATH}/bin:$HOME/.local/bin:$PATH"
  echo "VIRTUAL_ENV=${VENV_PATH}"
  echo "DJANGO_SETTINGS_MODULE=gyrinx.settings_dev"
} >> "$CLAUDE_ENV_FILE"
