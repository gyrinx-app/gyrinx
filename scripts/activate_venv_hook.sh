#!/bin/bash
# SessionStart hook: select the worktree virtualenv before each Bash call.
#
# CLAUDE_ENV_FILE is sourced on each call. Resolve the worktree from the current
# directory so worktree switches also change the interpreter and database.
# Worktrees under .claude/worktrees are provisioned on demand; dependency stamps
# trigger a re-sync after project metadata changes.
# See .claude/settings.json for hook registration.

set -euo pipefail

# CLAUDE_ENV_FILE is only available inside SessionStart hooks.  Variables
# written to it are injected into every subsequent Bash tool invocation.
if [ -z "${CLAUDE_ENV_FILE:-}" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Emit a minimal environment even when the worktree library is unavailable.
WORKTREE_LIB="${PROJECT_DIR}/scripts/lib/worktree.sh"
if [ -f "$WORKTREE_LIB" ]; then
  # shellcheck source=lib/worktree.sh
  source "$WORKTREE_LIB"
fi

# Resolve session constants once instead of on every Bash call.
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

# Provision worktrees selected before session startup. The emitted function
# handles worktree switches during the session.
if command -v provision_worktree_venv >/dev/null 2>&1; then
  START_WT=$(git -C "$PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null || true)
  if [ -n "$START_WT" ] && [ "$START_WT" != "$MAIN_WT" ] \
     && [[ "$START_WT" == *"/.claude/worktrees/"* ]]; then
    PATH="${HOME}/.local/bin:${PATH}" provision_worktree_venv "$START_WT" || true
  fi
fi

# Capture the pristine PATH (no venv prepended) so each invocation can
# rebuild PATH from a known base instead of accumulating duplicates.
BASE_PATH="$PATH"

# SessionStart also runs on resume and compaction. Do not append duplicate blocks.
MARKER="# >>> Gyrinx per-worktree venv activation >>>"
if grep -qF -- "$MARKER" "$CLAUDE_ENV_FILE" 2>/dev/null; then
  exit 0
fi

# Emit the dynamic block.  Constants determined at hook time are quoted via
# printf %q so they survive sourcing.  The heredoc body is single-quoted so
# $vars are evaluated at *source* time (per Bash call), not at hook-write
# time.
#
# Claude Code includes the emitted environment in wrapper process arguments.
# Strip comments so words in them cannot match unrelated pkill -f patterns.
{
  echo "$MARKER"
  printf 'export __GYRINX_BASE_PATH=%q\n' "$BASE_PATH"
  printf 'export __GYRINX_PG_BIN_DIR=%q\n' "$PG_BIN_DIR"
  printf 'export __GYRINX_MAIN_WT=%q\n' "$MAIN_WT"
  grep -Ev '^[[:space:]]*(#|$)' <<'BLOCK'
_gyrinx_activate_worktree() {
  local wt_root venv lib provision_failed=false

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

  # Pick the venv: worktree's own first, main worktree as fallback. Agent
  # worktrees under .claude/worktrees/ also re-sync after uv.lock changes.
  venv="${wt_root}/.venv"
  if [[ "$wt_root" == *"/.claude/worktrees/"* ]] \
     && command -v provision_worktree_venv >/dev/null 2>&1; then
    if ! PATH="${HOME}/.local/bin:${PATH}" \
      provision_worktree_venv "$wt_root" >&2; then
      provision_failed=true
      echo "[gyrinx] Worktree venv sync failed; leaving it inactive." >&2
    fi
  fi
  if [ "$provision_failed" = true ]; then
    venv=""
  elif [ ! -d "$venv" ]; then
    venv="${__GYRINX_MAIN_WT}/.venv"
  fi

  if [ -d "$venv" ]; then
    if [ -n "$__GYRINX_PG_BIN_DIR" ]; then
      export PATH="${__GYRINX_PG_BIN_DIR}:${venv}/bin:${HOME}/.local/bin:${__GYRINX_BASE_PATH}"
    else
      export PATH="${venv}/bin:${HOME}/.local/bin:${__GYRINX_BASE_PATH}"
    fi
    export VIRTUAL_ENV="$venv"
  else
    # A previous invocation may have activated this worktree's stale venv.
    # Restore the baseline instead of silently continuing to use it.
    if [ -n "$__GYRINX_PG_BIN_DIR" ]; then
      export PATH="${__GYRINX_PG_BIN_DIR}:${HOME}/.local/bin:${__GYRINX_BASE_PATH}"
    else
      export PATH="${HOME}/.local/bin:${__GYRINX_BASE_PATH}"
    fi
    unset VIRTUAL_ENV
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
BLOCK
  echo "# <<< Gyrinx per-worktree venv activation <<<"
} >> "$CLAUDE_ENV_FILE"
