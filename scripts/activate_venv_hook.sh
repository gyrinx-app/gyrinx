#!/bin/bash
# SessionStart hook: activate the correct per-worktree virtualenv for every
# Bash tool invocation, including mid-session worktree switches.
#
# The contents written to CLAUDE_ENV_FILE are sourced before every Bash tool
# call.  We therefore write a small bash function that re-evaluates the
# active worktree from the current working directory on every invocation —
# without that, an agent that calls EnterWorktree mid-session ends up running
# pre-commit / pytest / manage against the *main* worktree's venv, which
# breaks pre-commit hooks that import gyrinx (they see the main worktree's
# code, not the worktree the agent is actually editing).
#
# If a worktree under .claude/worktrees/ has no .venv yet, the function
# provisions one on demand via provision_worktree_venv in lib/worktree.sh
# (one-time ~1 min cost per worktree).
#
# Works in both local and remote (Claude Code on the Web) environments.
# See .claude/settings.json for hook registration.

set -euo pipefail

# CLAUDE_ENV_FILE is only available inside SessionStart hooks.  Variables
# written to it are injected into every subsequent Bash tool invocation.
if [ -z "${CLAUDE_ENV_FILE:-}" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Source the worktree library so we can resolve the main worktree path
# and (later) provision a venv if needed.  If the library is missing,
# we still emit a minimal env file so the session is usable.
WORKTREE_LIB="${PROJECT_DIR}/scripts/lib/worktree.sh"
if [ -f "$WORKTREE_LIB" ]; then
  # shellcheck source=lib/worktree.sh
  source "$WORKTREE_LIB"
fi

# Resolve the main worktree path (where the canonical .venv lives) and
# the Homebrew Postgres bin dir once at hook time.  These don't change
# during the session, so embedding them as constants avoids re-resolving
# on every Bash call.
MAIN_WT=""
if command -v _main_worktree >/dev/null 2>&1; then
  MAIN_WT=$(cd "$PROJECT_DIR" 2>/dev/null && _main_worktree || true)
fi
if [ -z "$MAIN_WT" ]; then
  MAIN_WT=$(git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null \
    | sed -n 's/^worktree //p' | head -1)
fi

PG_BIN_DIR=""
if command -v homebrew_postgres_bin >/dev/null 2>&1; then
  PG_BIN_DIR=$(homebrew_postgres_bin)
fi

# Eagerly provision the venv for the session's *starting* worktree.  This
# catches `isolation: "worktree"` subagents whose CWD is already a child
# worktree at session start.  For mid-session EnterWorktree the per-Bash
# function below handles it.
if command -v provision_worktree_venv >/dev/null 2>&1; then
  START_WT=$(git -C "$PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null || true)
  if [ -n "$START_WT" ] && [ "$START_WT" != "$MAIN_WT" ] \
     && [[ "$START_WT" == *"/.claude/worktrees/"* ]]; then
    provision_worktree_venv "$START_WT" || true
  fi
fi

# Capture the pristine PATH (no venv prepended) so each invocation can
# rebuild PATH from a known base instead of accumulating duplicates.
BASE_PATH="$PATH"

# Emit the dynamic block.  Constants determined at hook time are quoted via
# printf %q so they survive sourcing.  The heredoc body is single-quoted so
# $vars are evaluated at *source* time (per Bash call), not at hook-write
# time.
{
  echo "# >>> Gyrinx per-worktree venv activation >>>"
  printf 'export __GYRINX_BASE_PATH=%q\n' "$BASE_PATH"
  printf 'export __GYRINX_PG_BIN_DIR=%q\n' "$PG_BIN_DIR"
  printf 'export __GYRINX_MAIN_WT=%q\n' "$MAIN_WT"
  cat <<'BLOCK'
_gyrinx_activate_worktree() {
  local wt_root venv lib

  # Determine which worktree we're currently in.  Fall back to the main
  # worktree if cwd isn't a git checkout (e.g. the agent cd'd to /tmp).
  wt_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [ -z "$wt_root" ]; then
    wt_root="$__GYRINX_MAIN_WT"
  fi

  # Always source the *main* worktree's scripts/lib/worktree.sh — never the
  # current worktree's copy.  Two reasons:
  #   1. Trust boundary: sourcing the worktree's copy would auto-execute any
  #      unreviewed changes to that file on every Bash invocation.
  #   2. Staleness: older worktrees may have a worktree.sh from before
  #      provision_worktree_venv existed; sourcing them would silently
  #      disable auto-provisioning — the very failure mode this hook fixes.
  lib="${__GYRINX_MAIN_WT}/scripts/lib/worktree.sh"
  if [ -f "$lib" ]; then
    # shellcheck source=/dev/null
    . "$lib"
  fi

  # Pick the venv: worktree's own first, main worktree as fallback.  For
  # agent worktrees under .claude/worktrees/, auto-provision if missing so
  # `python`, `pre-commit`, `pytest`, etc. all see worktree-local code.
  venv="${wt_root}/.venv"
  if [ ! -d "$venv" ] \
     && [[ "$wt_root" == *"/.claude/worktrees/"* ]] \
     && command -v provision_worktree_venv >/dev/null 2>&1; then
    provision_worktree_venv "$wt_root" >&2 || true
  fi
  if [ ! -d "$venv" ]; then
    venv="${__GYRINX_MAIN_WT}/.venv"
  fi

  if [ -d "$venv" ]; then
    if [ -n "$__GYRINX_PG_BIN_DIR" ]; then
      export PATH="${__GYRINX_PG_BIN_DIR}:${venv}/bin:${HOME}/.local/bin:${__GYRINX_BASE_PATH}"
    else
      export PATH="${venv}/bin:${HOME}/.local/bin:${__GYRINX_BASE_PATH}"
    fi
    export VIRTUAL_ENV="$venv"
  fi

  export DJANGO_SETTINGS_MODULE=gyrinx.settings_dev

  # Per-worktree DB identity (DB_NAME / DJANGO_PORT / DB_CONFIG) — derived
  # from wt_root so mid-session EnterWorktree retargets the right database.
  if command -v worktree_db_name >/dev/null 2>&1 && [ -n "$wt_root" ]; then
    DB_NAME=$(worktree_db_name "$wt_root")
    DJANGO_PORT=$(worktree_port "$wt_root")
    export DB_NAME DJANGO_PORT
    export DB_HOST=localhost
    export DB_PORT=5432
    DB_CONFIG="$(db_config_for_local)"
    export DB_CONFIG
  fi
}
_gyrinx_activate_worktree
# <<< Gyrinx per-worktree venv activation <<<
BLOCK
} >> "$CLAUDE_ENV_FILE"
