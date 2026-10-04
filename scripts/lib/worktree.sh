#!/bin/bash
# Shared worktree utility library.
#
# Provides deterministic database names and Django ports for per-worktree
# isolation, the worktree Python interpreter used by git hook scripts, and
# stamped venv and React-asset provisioners. A hashed port that is already
# taken is recorded in logs/dev-port so later commands keep the same
# DJANGO_PORT. Sourced by dev.sh,
# activate_venv_hook.sh, .codex/run.sh, cleanup scripts, and pre-commit hook
# wrappers.
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

# worktree_hashed_port [path]
#   Main worktree  → 8000
#   Child worktree → deterministic port in range 8100-9599
worktree_hashed_port() {
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

# _worktree_saved_port <root>
#   logs/dev-port records a port chosen when the hash was already taken.
#   Session cookies are named for DJANGO_PORT, so every command must see it.
_worktree_saved_port() {
  local root="$1"
  local file="${root}/logs/dev-port"
  local saved
  [ -f "$file" ] || return 0
  saved=$(head -n 1 "$file" 2>/dev/null || true)
  saved=${saved//[[:space:]]/}
  if [[ "$saved" =~ ^[0-9]+$ ]] && [ "$saved" -ge 1024 ] && [ "$saved" -le 65535 ]; then
    echo "$saved"
  fi
}

# worktree_port [path]
#   The hashed port, unless logs/dev-port holds a port from a collision.
worktree_port() {
  local root="${1:-$(_worktree_root)}"
  local saved
  saved=$(_worktree_saved_port "$root")
  if [ -n "$saved" ]; then
    echo "$saved"
    return 0
  fi
  worktree_hashed_port "$root"
}

# port_is_listening <port>
#   True when the port is in use: something accepts on 127.0.0.1, or the
#   wildcard address cannot be bound. runserver binds 0.0.0.0, so a
#   listener on another local address still blocks it.
port_is_listening() {
  python3 -c 'import socket, sys
port = int(sys.argv[1])
s = socket.socket()
s.settimeout(0.2)
try:
    rc = s.connect_ex(("127.0.0.1", port))
finally:
    s.close()
if rc == 0:
    sys.exit(0)
b = socket.socket()
b.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    b.bind(("0.0.0.0", port))
except OSError:
    sys.exit(0)
finally:
    b.close()
sys.exit(1)' "$1"
}

# listening_pid <port>
#   PID of the process listening on 127.0.0.1:<port>, or empty.
listening_pid() {
  local port="$1"
  local pid=""
  if [ -r /proc/net/tcp ]; then
    pid=$(python3 - "$port" <<'PY'
import os
import sys

port = int(sys.argv[1])
hexport = f"{port:04X}"
inodes = set()
with open("/proc/net/tcp", encoding="ascii", errors="replace") as handle:
    next(handle, None)
    for line in handle:
        fields = line.split()
        if len(fields) < 10:
            continue
        local, state, inode = fields[1], fields[3], fields[9]
        local_port = local.rsplit(":", 1)[-1]
        if local_port.upper() == hexport and state == "0A":
            inodes.add(inode)
if not inodes:
    sys.exit(0)
for entry in os.listdir("/proc"):
    if not entry.isdigit():
        continue
    fd_dir = f"/proc/{entry}/fd"
    try:
        fds = os.listdir(fd_dir)
    except OSError:
        continue
    for fd in fds:
        try:
            target = os.readlink(f"{fd_dir}/{fd}")
        except OSError:
            continue
        if target.startswith("socket:[") and target[8:-1] in inodes:
            print(entry)
            sys.exit(0)
PY
)
  fi
  if [ -z "$pid" ] && command -v lsof >/dev/null 2>&1; then
    pid=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)
    pid=${pid%%$'\n'*}
  fi
  if [ -n "$pid" ]; then
    echo "$pid"
  fi
}

# listener_cwd <pid>
listener_cwd() {
  local pid="$1"
  if [ -d "/proc/${pid}" ]; then
    readlink -f "/proc/${pid}/cwd" 2>/dev/null || true
    return 0
  fi
  if command -v lsof >/dev/null 2>&1; then
    local cwd
    cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null || true)
    cwd=${cwd##*$'\n'n}
    cwd=${cwd%%$'\n'*}
    echo "$cwd"
  fi
}

# listener_cmd <pid>
listener_cmd() {
  local pid="$1"
  if [ -r "/proc/${pid}/cmdline" ]; then
    tr '\0' ' ' < "/proc/${pid}/cmdline" || true
    return 0
  fi
  ps -p "$pid" -o args= 2>/dev/null || true
}

# dev_port_owner <root> <port>
#   ours: this worktree's runserver. other: a different process. unknown: no pid.
dev_port_owner() {
  local root="$1"
  local port="$2"
  local pid cwd cmd root_phys
  pid=$(listening_pid "$port")
  if [ -z "$pid" ]; then
    echo unknown
    return 0
  fi
  root_phys=$(cd "$root" && pwd -P)
  cwd=$(listener_cwd "$pid")
  cmd=$(listener_cmd "$pid")
  if [[ "$cmd" != *runserver* ]]; then
    echo other
    return 0
  fi
  if [ "$cwd" = "$root_phys" ] || [[ "$cwd" == "$root_phys"/* ]] \
    || [[ "$cmd" == *"$root_phys/"* ]] || [[ "$cmd" == *"$root/"* ]]; then
    echo ours
    return 0
  fi
  echo other
}

# next_free_dev_port <start>
#   The next port that is not accepting connections. Skips 8000.
next_free_dev_port() {
  local start="$1"
  local i candidate
  for ((i = 1; i <= 32; i++)); do
    candidate=$((start + i))
    if [ "$candidate" -gt 65535 ] || [ "$candidate" -eq 8000 ]; then
      continue
    fi
    if ! port_is_listening "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  for ((i = 0; i < 32; i++)); do
    candidate=$((9600 + i))
    if [ "$candidate" -eq "$start" ]; then
      continue
    fi
    if ! port_is_listening "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

# choose_dev_port <root> <preferred>
#   Prints the port to bind. Exit 10 when this worktree is already serving it.
#   A sibling that hashed to the same port is recorded in logs/dev-port.
choose_dev_port() {
  local root="$1"
  local port="$2"
  local owner replacement
  if ! port_is_listening "$port"; then
    echo "$port"
    return 0
  fi
  owner=$(dev_port_owner "$root" "$port")
  if [ "$owner" = "ours" ]; then
    echo "This worktree is already serving http://localhost:${port}." >&2
    echo "$port"
    return 10
  fi
  if [ "$owner" = "unknown" ]; then
    echo "Port ${port} is already in use, and this script cannot tell which process has it." >&2
    echo "Session cookies are named for DJANGO_PORT. Record a free port and start again:" >&2
    echo "  mkdir -p logs && echo <free-port> > logs/dev-port && ./scripts/dev.sh" >&2
    echo "Then re-source .venv/bin/activate so screenshots and manage agent_login_url use it." >&2
    return 1
  fi
  replacement=$(next_free_dev_port "$port") || {
    echo "Port ${port} is already in use, and no nearby port is free." >&2
    return 1
  }
  mkdir -p "${root}/logs"
  printf '%s\n' "$replacement" > "${root}/logs/dev-port"
  echo "Port ${port} is already in use by another process." >&2
  echo "This worktree will listen on ${replacement} instead." >&2
  echo "Session cookies use that port. Screenshots and login links read logs/dev-port." >&2
  echo "Delete logs/dev-port to return to the hashed port once it is free." >&2
  echo "$replacement"
}

# resolve_dev_port [path]
#   choose_dev_port for this worktree's current port (hash or logs/dev-port).
resolve_dev_port() {
  local root="${1:-$(_worktree_root)}"
  choose_dev_port "$root" "$(worktree_port "$root")"
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

# worktree_python [path]
#   Print the Python interpreter for this worktree. Prefers
#   <root>/.venv/bin/python so script-language pre-commit hooks still run
#   when the caller has no interpreter on PATH — a plain `git commit`
#   otherwise dies in the migration check. Falls back to python3, then
#   python, from PATH.
worktree_python() {
  local wt_root="${1:-$(_worktree_root)}"
  local candidate
  if [ -n "$wt_root" ] && [ -x "${wt_root}/.venv/bin/python" ]; then
    printf '%s\n' "${wt_root}/.venv/bin/python"
    return 0
  fi
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  echo "No Python interpreter found. Create .venv (uv sync --locked or .codex/setup.sh) or put python3 on PATH." >&2
  echo "Codex: .codex/run.sh git commit -m '...' still works if a hook needs the full worktree env." >&2
  return 1
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

# _release_provision_lock <lock_dir> <label>
#   Remove this process's mkdir lock. A waiter may delete the directory, or
#   claim it, in the gap after the pid file is gone. That handoff is success:
#   the work this process finished is already done. Fail only when this
#   process still holds a directory it cannot remove.
#   _provision_lock_handoff_hook, when defined, runs in that gap so a test
#   can take the lock before rmdir.
_release_provision_lock() {
  local lock_dir="$1"
  local label="$2"
  local holder=""

  if [ -f "$lock_dir/pid" ]; then
    read -r holder < "$lock_dir/pid" || holder=""
    if [ "$holder" = "$$" ]; then
      rm -f "$lock_dir/pid"
    fi
  fi
  if declare -F _provision_lock_handoff_hook >/dev/null 2>&1; then
    _provision_lock_handoff_hook "$lock_dir"
  fi
  if [ ! -d "$lock_dir" ]; then
    return 0
  fi
  if rmdir "$lock_dir" 2>/dev/null; then
    return 0
  fi
  if [ ! -d "$lock_dir" ]; then
    return 0
  fi
  holder=""
  if [ -f "$lock_dir/pid" ]; then
    read -r holder < "$lock_dir/pid" || holder=""
  fi
  if [ -n "$holder" ] && [ "$holder" != "$$" ]; then
    return 0
  fi
  echo "[gyrinx] Could not release the ${label}." >&2
  return 1
}

# provision_worktree_venv <worktree_root> [reset]
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
  local reset_venv="${2:-false}"
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
  # Bump the prefix whenever the verification represented by a stamp changes.
  current_inputs="v2:${lock_hash}:${project_hash}"
  if [ -f "$stamp_file" ]; then
    stamped_inputs=$(<"$stamp_file")
  fi
  if [ "$reset_venv" != true ] && [ -d "$venv" ] \
    && [ "$stamped_inputs" = "$current_inputs" ]; then
    return 0
  fi

  # Only serialize the slow path. A second caller rechecks the stamp after it
  # acquires the lock, so concurrent startup performs at most one uv sync.
  local lock_dir="${wt_root}/.gyrinx-venv-provision.lock"
  local lock_pid attempts=0
  while ! mkdir "$lock_dir" 2>/dev/null; do
    lock_pid=""
    if [ -f "$lock_dir/pid" ]; then
      read -r lock_pid < "$lock_dir/pid" || lock_pid=""
    fi
    if [[ "$lock_pid" =~ ^[0-9]+$ ]] && ! kill -0 "$lock_pid" 2>/dev/null; then
      if rm "$lock_dir/pid" 2>/dev/null && rmdir "$lock_dir" 2>/dev/null; then
        attempts=0
        continue
      fi
    fi
    attempts=$((attempts + 1))
    # Recover the empty directory left if its owner died between mkdir and
    # writing the PID. rmdir remains safe if a live owner writes it meanwhile.
    if [ "$attempts" -ge 10 ] && [ ! -e "$lock_dir/pid" ] \
      && rmdir "$lock_dir" 2>/dev/null; then
      attempts=0
      continue
    fi
    if [ "$attempts" -ge 1200 ]; then
      echo "[gyrinx] Timed out waiting to provision ${venv}." >&2
      return 1
    fi
    sleep 0.1
  done
  if ! printf '%s\n' "$$" > "$lock_dir/pid"; then
    rmdir "$lock_dir" 2>/dev/null || true
    echo "[gyrinx] Could not initialise the provisioning lock for ${venv}." >&2
    return 1
  fi

  local provision_status
  if (
    stamped_inputs=""
    if [ -f "$stamp_file" ]; then
      stamped_inputs=$(<"$stamp_file")
    fi
    if [ "$reset_venv" != true ] && [ -d "$venv" ] \
      && [ "$stamped_inputs" = "$current_inputs" ]; then
      return 0
    fi
    if ! command -v uv >/dev/null 2>&1; then
      echo "[gyrinx] uv not on PATH; cannot auto-provision ${venv}." >&2
      echo "[gyrinx] Install uv (https://docs.astral.sh/uv/) then re-run, or:" >&2
      echo "[gyrinx]   cd '${wt_root}' && UV_PROJECT_ENVIRONMENT='${venv}' uv sync --locked" >&2
      return 1
    fi
    if [ "$reset_venv" = true ] && [ -d "$venv" ]; then
      echo "[gyrinx] Removing existing per-worktree venv at ${venv}..." >&2
      if ! rm -rf "$venv"; then
        return 1
      fi
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
    if ! (cd / && "$venv/bin/python" -c "import gyrinx, n23" >/dev/null 2>&1); then
      echo "[gyrinx] Editable install is stale; reinstalling the project..." >&2
      if ! (cd "$wt_root" && UV_PROJECT_ENVIRONMENT="$venv" \
            uv sync --locked --quiet --reinstall-package gyrinx); then
        if [ "$new_venv" = true ]; then
          rm -rf "$venv"
        fi
        return 1
      fi
      if ! (cd / && "$venv/bin/python" -c "import gyrinx, n23" >/dev/null 2>&1); then
        echo "[gyrinx] Project imports still fail after reinstalling ${venv}." >&2
        if [ "$new_venv" = true ]; then
          rm -rf "$venv"
        fi
        return 1
      fi
    fi
    if ! printf '%s\n' "$current_inputs" > "$stamp_file"; then
      echo "[gyrinx] Could not record dependency state in ${stamp_file}." >&2
      if [ "$new_venv" = true ]; then
        rm -rf "$venv"
      fi
      return 1
    fi
    install_worktree_venv_hook "$venv/bin/activate" || true
    if [ "$new_venv" = true ]; then
      echo "[gyrinx] Provisioned ${venv}." >&2
    else
      echo "[gyrinx] Synced ${venv}." >&2
    fi
    return 0
  ); then
    provision_status=0
  else
    provision_status=$?
  fi
  if ! _release_provision_lock "$lock_dir" "provisioning lock for ${venv}"; then
    return 1
  fi
  return "$provision_status"
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

# _frontend_inputs_newer <worktree_root> <than>
#   True when an input to `npm run js` is newer than <than>. That command
#   exports Cotton recipes before Vite runs, so the scan covers island source,
#   Cotton templates, and the icon modules the exporter reads.
_frontend_inputs_newer() {
  local wt_root="$1"
  local than="$2"
  local roots=()
  if [ -d "${wt_root}/n26/frontend" ]; then
    roots+=("${wt_root}/n26/frontend")
  fi
  if [ -d "${wt_root}/n26/core/templates/cotton" ]; then
    roots+=("${wt_root}/n26/core/templates/cotton")
  fi
  if [ "${#roots[@]}" -gt 0 ] \
    && [ -n "$(find "${roots[@]}" -type f \
      ! -path '*/generated/*' \
      -newer "$than" -print -quit 2>/dev/null)" ]; then
    return 0
  fi
  local file
  for file in \
    "${wt_root}/n26/core/icons.py" \
    "${wt_root}/n26/core/brand_icons.py"
  do
    if [ -f "$file" ] && [ "$file" -nt "$than" ]; then
      return 0
    fi
  done
  return 1
}

# _frontend_repair_plan <worktree_root>
#   Prints "install", "js", or "install js" when node_modules or the React
#   manifest needs recovery. Prints nothing when both are current.
_frontend_repair_plan() {
  local wt_root="$1"
  local manifest="${wt_root}/n26/core/static/n26/react/manifest.json"
  local install=false
  local js=false
  if [ ! -d "${wt_root}/node_modules" ] \
    || [ "${wt_root}/package-lock.json" -nt "${wt_root}/node_modules" ] \
    || [ "${wt_root}/package.json" -nt "${wt_root}/node_modules" ]; then
    install=true
  fi
  if [ ! -f "$manifest" ] \
    || [ "${wt_root}/package-lock.json" -nt "$manifest" ] \
    || [ "${wt_root}/package.json" -nt "$manifest" ] \
    || [ "${wt_root}/vite.config.mts" -nt "$manifest" ]; then
    js=true
  elif _frontend_inputs_newer "$wt_root" "$manifest"; then
    js=true
  fi
  if [ "$install" = true ] && [ "$js" = true ]; then
    printf 'install js\n'
  elif [ "$install" = true ]; then
    printf 'install\n'
  elif [ "$js" = true ]; then
    printf 'js\n'
  fi
  return 0
}

# provision_worktree_frontend <worktree_root>
#   After a rebase, node_modules and the gitignored React manifest can be
#   older than package-lock.json, n26/frontend, Cotton templates, or icon
#   sources. Codex commands go through .codex/run.sh rather than
#   ./scripts/dev.sh, so this helper does the same recovery there: `npm ci`
#   when the install is stale, then `npm run js` when the manifest is missing
#   or stale. Both commands put the worktree venv first on PATH because
#   `npm run js` starts with `python -m n26.frontend.tooling.export_cotton_recipes`.
#
#   The freshness check and the install/build share one lock, matching
#   provision_worktree_venv, so two Codex commands cannot npm ci at once.
#   Uses `npm ci --no-audit --no-fund`, never `npm audit fix`. A checkout
#   without vite.config.mts is a no-op so pre-islands fixtures stay quiet.
#   Returns 0 on success or skip; non-zero if npm/python/lockfile is missing
#   when a build is required, or if ci/js fails.
provision_worktree_frontend() {
  local wt_root="$1"
  if [ -z "$wt_root" ] || [ ! -d "$wt_root" ]; then
    return 1
  fi
  if [ ! -f "${wt_root}/vite.config.mts" ]; then
    return 0
  fi

  if [ -x "${wt_root}/.venv/bin/python" ]; then
    PATH="${wt_root}/.venv/bin:${PATH}"
    export PATH
  fi

  local plan
  plan=$(_frontend_repair_plan "$wt_root")
  if [ -z "$plan" ]; then
    return 0
  fi

  local lock_dir="${wt_root}/.gyrinx-frontend-provision.lock"
  local lock_pid attempts=0
  while ! mkdir "$lock_dir" 2>/dev/null; do
    lock_pid=""
    if [ -f "$lock_dir/pid" ]; then
      read -r lock_pid < "$lock_dir/pid" || lock_pid=""
    fi
    if [[ "$lock_pid" =~ ^[0-9]+$ ]] && ! kill -0 "$lock_pid" 2>/dev/null; then
      if rm "$lock_dir/pid" 2>/dev/null && rmdir "$lock_dir" 2>/dev/null; then
        attempts=0
        continue
      fi
    fi
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 10 ] && [ ! -e "$lock_dir/pid" ] \
      && rmdir "$lock_dir" 2>/dev/null; then
      attempts=0
      continue
    fi
    if [ "$attempts" -ge 1200 ]; then
      echo "[gyrinx] Timed out waiting to provision frontend assets in ${wt_root}." >&2
      return 1
    fi
    sleep 0.1
  done
  if ! printf '%s\n' "$$" > "$lock_dir/pid"; then
    rmdir "$lock_dir" 2>/dev/null || true
    echo "[gyrinx] Could not initialise the frontend provisioning lock for ${wt_root}." >&2
    return 1
  fi

  local provision_status
  if (
    plan=$(_frontend_repair_plan "$wt_root")
    if [ -z "$plan" ]; then
      return 0
    fi
    if [ ! -f "${wt_root}/package-lock.json" ]; then
      echo "[gyrinx] No package-lock.json at ${wt_root}; cannot install frontend deps." >&2
      return 1
    fi
    if ! command -v npm >/dev/null 2>&1; then
      echo "[gyrinx] npm is not on PATH; cannot rebuild React assets." >&2
      echo "[gyrinx] Install Node, then from ${wt_root} run:" >&2
      echo "[gyrinx]   npm ci --no-audit --no-fund" >&2
      echo "[gyrinx]   PATH=\"${wt_root}/.venv/bin:\$PATH\" npm run js" >&2
      return 1
    fi
    case " $plan " in
      *" install "*)
        echo "[gyrinx] Installing npm dependencies with npm ci (node_modules missing or out of date)..." >&2
        if ! (cd "$wt_root" && npm ci --no-audit --no-fund); then
          echo "[gyrinx] npm ci failed. Do not run npm audit fix unless the task is the audit itself." >&2
          return 1
        fi
        ;;
    esac
    case " $plan " in
      *" js "*)
        if ! command -v python >/dev/null 2>&1; then
          echo "[gyrinx] python is not on PATH; npm run js needs the worktree venv." >&2
          echo "[gyrinx]   PATH=\"${wt_root}/.venv/bin:\$PATH\" npm run js" >&2
          echo "[gyrinx] or: .codex/run.sh npm run js" >&2
          return 1
        fi
        echo "[gyrinx] Building React islands (manifest missing or out of date)..." >&2
        if ! (cd "$wt_root" && npm run js); then
          echo "[gyrinx] npm run js failed. Rebuild with the worktree venv on PATH:" >&2
          echo "[gyrinx]   PATH=\"${wt_root}/.venv/bin:\$PATH\" npm run js" >&2
          echo "[gyrinx] or: .codex/run.sh npm run js" >&2
          echo "[gyrinx] Do not run npm audit fix unless the task is the audit itself." >&2
          return 1
        fi
        ;;
    esac
    return 0
  ); then
    provision_status=0
  else
    provision_status=$?
  fi
  if ! _release_provision_lock "$lock_dir" \
    "frontend provisioning lock for ${wt_root}"; then
    return 1
  fi
  return "$provision_status"
}
