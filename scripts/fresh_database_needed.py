#!/usr/bin/env python3
"""Say whether a change can break applying the migration graph from scratch.

The fresh-database CI job migrates an empty database. On a pull request it
only needs to when the change touches something that apply depends on:

- a migration file; an app's apps.py, whose label every dependency names;
  the settings that list the apps in the graph; the dependency lock, since a
  Django upgrade can retire an operation an old migration still uses;
- a project module that a migration imports (an icon table, a field type,
  a model package a data migration reads through), or a package above one.

Prints the matching paths, one per line, and nothing when there are none.
Imports one level deep are read straight out of the migration files, so the
set follows the migrations as they are written; what those modules import in
turn is not followed.

    scripts/fresh_database_needed.py            # against origin/main
    scripts/fresh_database_needed.py origin/dev # against another base

Runs on the system interpreter before the project's environment exists, so it
uses the standard library only.
"""

import pathlib
import re
import subprocess  # nosec B404 — runs one fixed git command to list changed files
import sys
from collections.abc import Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent

ALWAYS = (
    re.compile(r"(^|/)migrations/[^/]+\.py$"),
    re.compile(r"(^|/)apps\.py$"),
    re.compile(r"^gyrinx/settings"),
    re.compile(r"^uv\.lock$"),
)

PROJECT_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+((?:n23|n26|gyrinx)(?:\.[A-Za-z0-9_]+)*)", re.MULTILINE
)


def migration_imports(root: pathlib.Path = ROOT) -> set[str]:
    """Project modules the migrations import, as repo-relative paths sans .py."""
    found: set[str] = set()
    for migration in root.glob("*/*/migrations/*.py"):
        for module in PROJECT_IMPORT.findall(migration.read_text(encoding="utf-8")):
            found.add(module.replace(".", "/"))
    return found


def module_path(changed_file: str) -> str:
    path = pathlib.PurePosixPath(changed_file)
    if path.name == "__init__.py":
        return path.parent.as_posix()
    return path.with_suffix("").as_posix()


def touches_import(changed_file: str, imports: Iterable[str]) -> bool:
    changed = module_path(changed_file)
    for module in imports:
        if changed == module or changed.startswith(module + "/"):
            return True
        if module.startswith(changed + "/"):
            # A package whose __init__ runs when the module beneath it loads.
            return True
    return False


def paths_needing_fresh_migrate(
    changed_files: Iterable[str], imports: Iterable[str]
) -> list[str]:
    imports = list(imports)
    matched = []
    for path in changed_files:
        if any(pattern.search(path) for pattern in ALWAYS):
            matched.append(path)
        elif path.endswith(".py") and touches_import(path, imports):
            matched.append(path)
    return matched


def changed_files_against(base: str) -> list[str]:
    out = subprocess.run(  # nosec B607 — fixed argv; git resolved from PATH like every repo tool
        [
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=AMD",
            f"{base}...HEAD",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else "origin/main"
    changed = changed_files_against(base)
    for path in paths_needing_fresh_migrate(changed, migration_imports()):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
