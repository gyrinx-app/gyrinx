#!/bin/bash
# Hide untracked migration modules for one check, then put them back.
#
# pre-commit copies the index over tracked files and leaves untracked files
# in place. A migration that belongs to those cleared edits stays in the
# graph, so makemigrations --check asks for a migration that undoes it.
# The commit does not include untracked files, so the hook hides migration
# modules (a *.py file whose parent directory is named migrations) and
# restores them when the check exits, including on failure. A manual run
# does not pass --pre-commit and still sees those files.

_UNTRACKED_MIGRATIONS_DIR=""

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
  if [[ "${1:-}" != "--pre-commit" && "${PRE_COMMIT:-}" != "1" ]]; then
    return 0
  fi
  git rev-parse --is-inside-work-tree >/dev/null
  while IFS= read -r -d '' path; do
    _is_migration_module "$path" || continue
    if [[ -z "$_UNTRACKED_MIGRATIONS_DIR" ]]; then
      _UNTRACKED_MIGRATIONS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gyrinx-untracked-migrations.XXXXXX")"
    fi
    mkdir -p -- "$_UNTRACKED_MIGRATIONS_DIR/$(dirname -- "$path")"
    mv -- "$path" "$_UNTRACKED_MIGRATIONS_DIR/$path"
  done < <(git ls-files --others --exclude-standard -z)
}

restore_untracked_migrations() {
  local dir file rel
  dir="${_UNTRACKED_MIGRATIONS_DIR:-}"
  [[ -n "$dir" && -d "$dir" ]] || return 0
  while IFS= read -r -d '' file; do
    rel="${file#"$dir"/}"
    mkdir -p -- "$(dirname -- "$rel")"
    mv -- "$file" "$rel"
  done < <(find "$dir" -type f -print0)
  rm -rf -- "$dir"
  _UNTRACKED_MIGRATIONS_DIR=""
}
