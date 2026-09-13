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

_sha256_file() {
  local file="$1"
  local hash_output file_hash
  if command -v sha256sum >/dev/null 2>&1; then
    hash_output=$(sha256sum "$file") || return 1
  elif command -v shasum >/dev/null 2>&1; then
    hash_output=$(shasum -a 256 "$file") || return 1
  else
    return 1
  fi
  file_hash=${hash_output%%[[:space:]]*}
  if [[ ! "$file_hash" =~ ^[[:xdigit:]]{64}$ ]]; then
    return 1
  fi
  printf '%s\n' "$file_hash"
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

# provision_worktree_venv <worktree_root>
#   Ensure <worktree_root>/.venv matches uv.lock and pyproject.toml, and has
#   the project editable-installed from that worktree. A hash stamp makes the
#   unchanged case a cheap no-op while still catching dependency-input changes
#   after a rebase.
#
#   Used by dev.sh and activate_venv_hook.sh to give every child worktree
#   (including the .claude/worktrees/* worktrees created by EnterWorktree)
#   its own venv, so `import gyrinx` resolves to worktree-local code and
#   pre-commit hooks see the worktree's migrations / models.  Without this,
#   the main venv's editable install can get repointed to a child worktree
#   by an errant `uv sync` run without UV_PROJECT_ENVIRONMENT, corrupting every other
#   session.  See issue #1772.
#
#   Echoes a one-line progress message to stderr when a sync is needed so the
#   delay isn't silent. Returns 0 on success or skip; non-zero if uv is missing,
#   dependency inputs cannot be hashed, or provisioning fails.
provision_worktree_venv() {
  local wt_root="$1"
  if [ -z "$wt_root" ] || [ ! -d "$wt_root" ]; then
    return 1
  fi
  local venv="${wt_root}/.venv"
  local lock_file="${wt_root}/uv.lock"
  local project_file="${wt_root}/pyproject.toml"
  local stamp_file="${venv}/.gyrinx-uv-inputs"
  local lock_hash project_hash current_inputs stamped_inputs=""
  if [ ! -f "$lock_file" ]; then
    echo "[gyrinx] No uv.lock found at ${lock_file}; cannot provision ${venv}." >&2
    return 1
  fi
  if [ ! -f "$project_file" ]; then
    echo "[gyrinx] No pyproject.toml found at ${project_file}; cannot provision ${venv}." >&2
    return 1
  fi
  if ! lock_hash=$(_sha256_file "$lock_file"); then
    echo "[gyrinx] Could not hash ${lock_file}; cannot verify ${venv}." >&2
    return 1
  fi
  if ! project_hash=$(_sha256_file "$project_file"); then
    echo "[gyrinx] Could not hash ${project_file}; cannot verify ${venv}." >&2
    return 1
  fi
  current_inputs="${lock_hash}:${project_hash}"
  if [ -f "$stamp_file" ]; then
    stamped_inputs=$(<"$stamp_file")
  fi
  if [ -d "$venv" ] && [ "$stamped_inputs" = "$current_inputs" ]; then
    return 0
  fi
  if ! command -v uv >/dev/null 2>&1; then
    echo "[gyrinx] uv not on PATH; cannot auto-provision ${venv}." >&2
    echo "[gyrinx] Install uv (https://docs.astral.sh/uv/) then re-run, or:" >&2
    echo "[gyrinx]   cd '${wt_root}' && UV_PROJECT_ENVIRONMENT='${venv}' uv sync --locked" >&2
    return 1
  fi
  local new_venv=false
  if [ ! -d "$venv" ]; then
    new_venv=true
    echo "[gyrinx] Provisioning per-worktree venv at ${venv} (~1 min)..." >&2
  else
    echo "[gyrinx] Project dependency inputs changed; syncing ${venv}..." >&2
  fi
  # If initial provisioning fails after `uv sync` creates the directory,
  # remove the partial venv. Preserve an existing venv after a failed re-sync,
  # but leave its old stamp in place so the next call retries.
  # UV_PROJECT_ENVIRONMENT keeps `uv sync` pointed at this worktree's venv rather
  # than the default ./.venv, which is what stops it repointing another
  # worktree's editable install.  --locked installs exactly uv.lock.
  if ! (cd "$wt_root" && UV_PROJECT_ENVIRONMENT="$venv" uv sync --locked --quiet); then
    if [ "$new_venv" = true ]; then
      rm -rf "$venv"
    fi
    return 1
  fi
  printf '%s\n' "$current_inputs" > "$stamp_file"
  install_worktree_venv_hook "$venv/bin/activate" || true
  if [ "$new_venv" = true ]; then
    echo "[gyrinx] Provisioned ${venv}." >&2
  else
    echo "[gyrinx] Synced ${venv}." >&2
  fi
  return 0
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
