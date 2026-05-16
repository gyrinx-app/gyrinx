#!/bin/bash
# Shared worktree utility library.
#
# Provides deterministic database names and Django ports for per-worktree
# isolation.  Sourced by dev.sh, activate_venv_hook.sh, and cleanup scripts.
#
# Usage:
#   source scripts/lib/worktree.sh
#   DB_NAME=$(worktree_db_name)
#   PORT=$(worktree_port)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_worktree_root() {
  git rev-parse --show-toplevel 2>/dev/null
}

_main_worktree() {
  # The main worktree is the first stanza of `git worktree list --porcelain`,
  # which begins with `worktree <path>`.  Use --porcelain so paths containing
  # spaces aren't truncated by field-splitting.
  git worktree list --porcelain | sed -n 's/^worktree //p' | head -1
}

_is_main_worktree() {
  local root main
  root=$(_worktree_root)
  main=$(_main_worktree)
  [ "$root" = "$main" ]
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# worktree_db_name [path]
#   Main worktree  → gyrinx_main
#   Child worktree → gyrinx_wt_{8-char md5 hash of absolute path}
worktree_db_name() {
  local root="${1:-$(_worktree_root)}"
  local main
  main=$(_main_worktree)

  if [ "$root" = "$main" ]; then
    echo "gyrinx_main"
  else
    local hash
    hash=$(echo -n "$root" | md5 -q 2>/dev/null || echo -n "$root" | md5sum | awk '{print $1}')
    echo "gyrinx_wt_${hash:0:8}"
  fi
}

# worktree_port [path]
#   Main worktree  → 8000
#   Child worktree → deterministic port in range 8100-9599
worktree_port() {
  local root="${1:-$(_worktree_root)}"
  local main
  main=$(_main_worktree)

  if [ "$root" = "$main" ]; then
    echo 8000
  else
    local cksum_val
    cksum_val=$(echo -n "$root" | cksum | awk '{print $1}')
    echo $(( (cksum_val % 1500) + 8100 ))
  fi
}

# worktree_label [path]
#   Main worktree  → "main"
#   Child worktree → directory basename (e.g. "funny-kalam")
worktree_label() {
  local root="${1:-$(_worktree_root)}"
  local main
  main=$(_main_worktree)
  if [ "$root" = "$main" ]; then
    echo "main"
  else
    basename "$root"
  fi
}

# db_config_for_local
#   Returns the DB_CONFIG JSON for local Homebrew Postgres (trust auth).
#   Emits compact JSON (no spaces) so the value survives env-file / shell
#   round-tripping without quoting tricks.
db_config_for_local() {
  echo "{\"user\":\"$(whoami)\",\"password\":\"\"}"
}

# homebrew_postgres_bin
#   Resolves the bin directory for postgresql@16, working on both Apple
#   Silicon (/opt/homebrew) and Intel (/usr/local) Homebrew layouts.  Prints
#   nothing if Postgres 16 can't be located.
homebrew_postgres_bin() {
  local prefix=""
  if command -v brew >/dev/null 2>&1; then
    prefix=$(brew --prefix postgresql@16 2>/dev/null || true)
  fi
  if [ -z "$prefix" ]; then
    for candidate in /opt/homebrew/opt/postgresql@16 /usr/local/opt/postgresql@16; do
      if [ -d "$candidate" ]; then
        prefix="$candidate"
        break
      fi
    done
  fi
  if [ -n "$prefix" ] && [ -d "$prefix/bin" ]; then
    echo "$prefix/bin"
  fi
}

# homebrew_postgres_data_dir
#   Resolves the data directory for postgresql@16 (PGDATA).  Returns empty
#   string if it can't be located.
homebrew_postgres_data_dir() {
  local bin prefix
  bin=$(homebrew_postgres_bin)
  if [ -z "$bin" ]; then
    return
  fi
  prefix="${bin%/opt/postgresql@16/bin}"
  if [ -d "$prefix/var/postgresql@16" ]; then
    echo "$prefix/var/postgresql@16"
  fi
}

# install_worktree_venv_hook <activate_path>
#   Append the per-worktree DB env block to a venv's bin/activate file so
#   `source .venv/bin/activate` exports DB_NAME / DJANGO_PORT / DB_CONFIG
#   for the current worktree.  Idempotent — does nothing if the marker is
#   already present.
#
#   Returns 0 on success or skip-when-already-installed.
#   Returns 1 if the activate file doesn't exist.
install_worktree_venv_hook() {
  local activate="$1"
  local marker="# >>> Gyrinx per-worktree DB env >>>"
  if [ ! -f "$activate" ]; then
    return 1
  fi
  if grep -qF "$marker" "$activate"; then
    return 0
  fi
  cat >> "$activate" <<'BLOCK'

# >>> Gyrinx per-worktree DB env >>>
# Installed by scripts/setup-local-postgres.sh or scripts/dev.sh.  Makes
# pytest, manage, and other tools target the current worktree's Postgres
# database without manual exports.  Re-source the activate script after
# `cd`ing between worktrees.
_gyrinx_set_db_env() {
  local wt_root lib
  wt_root=$(git rev-parse --show-toplevel 2>/dev/null) || return 0
  lib="$wt_root/scripts/lib/worktree.sh"
  [ -f "$lib" ] || return 0
  # POSIX `.` rather than bash-only `source` — the activate script is also
  # used from zsh/ksh.
  # shellcheck source=/dev/null
  . "$lib"
  export DB_NAME
  DB_NAME=$(worktree_db_name "$wt_root")
  export DJANGO_PORT
  DJANGO_PORT=$(worktree_port "$wt_root")
  export DB_HOST=localhost
  export DB_PORT=5432
  export DB_CONFIG
  DB_CONFIG="$(db_config_for_local)"
}
_gyrinx_set_db_env
unset -f _gyrinx_set_db_env
# <<< Gyrinx per-worktree DB env <<<
BLOCK
  return 0
}
