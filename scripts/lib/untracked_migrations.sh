#!/bin/bash
# Hide untracked migration modules for one check, then put them back.
#
# pre-commit copies the index over tracked files and leaves untracked files
# in place. A migration that belongs to those cleared edits stays in the
# graph, so makemigrations --check asks for a migration that undoes it.
# The commit does not include untracked files, so the hook hides migration
# modules (a *.py file or link whose parent directory is named migrations)
# and restores them when the check exits, including on failure. A manual run
# does not pass --pre-commit and still sees those files.
#
# They wait under the repository's git directory, not /tmp. If the check is
# killed before it can restore them, they are still with the repository, and
# nothing deletes them.

_UNTRACKED_MIGRATIONS_DIR=""
_UNTRACKED_MIGRATIONS=()

_is_migration_module() {
  local path="$1"
  local parent
  [[ "$path" == *.py ]] || return 1
  parent="$(dirname -- "$path")"
  [[ "$(basename -- "$parent")" == "migrations" ]]
}

hide_untracked_migrations() {
  local path
  _UNTRACKED_MIGRATIONS_DIR=""
  _UNTRACKED_MIGRATIONS=()
  if [[ "${1:-}" != "--pre-commit" && "${PRE_COMMIT:-}" != "1" ]]; then
    return 0
  fi
  git rev-parse --is-inside-work-tree >/dev/null
  while IFS= read -r -d '' path; do
    _is_migration_module "$path" || continue
    if [[ -z "$_UNTRACKED_MIGRATIONS_DIR" ]]; then
      _UNTRACKED_MIGRATIONS_DIR="$(mktemp -d "$(git rev-parse --absolute-git-dir)/gyrinx-untracked-migrations.XXXXXX")"
    fi
    mkdir -p -- "$_UNTRACKED_MIGRATIONS_DIR/$(dirname -- "$path")"
    mv -- "$path" "$_UNTRACKED_MIGRATIONS_DIR/$path"
    _UNTRACKED_MIGRATIONS+=("$path")
  done < <(git ls-files --others --exclude-standard -z)
}

# Put back exactly the paths hide moved, links included. If one cannot go
# back, leave the directory in place and say where it is.
restore_untracked_migrations() {
  local dir path stuck=0
  dir="${_UNTRACKED_MIGRATIONS_DIR:-}"
  [[ -n "$dir" && -d "$dir" ]] || return 0
  for path in "${_UNTRACKED_MIGRATIONS[@]}"; do
    mkdir -p -- "$(dirname -- "$path")"
    mv -- "$dir/$path" "$path" || stuck=1
  done
  if [[ "$stuck" == "1" ]]; then
    echo "Some untracked migrations were not put back. They are in $dir" >&2
    return 1
  fi
  rm -rf -- "$dir"
  _UNTRACKED_MIGRATIONS_DIR=""
  _UNTRACKED_MIGRATIONS=()
}
