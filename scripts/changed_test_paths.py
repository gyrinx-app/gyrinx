#!/usr/bin/env python3
"""Print the test paths a change touched, for the required CI test job.

The required job runs `pytest -m core` plus whatever tests the pull request
itself touched. This script works out the second half:

- a test file that was added or modified is listed as itself;
- a changed `conftest.py` lists its directory, so every test under it runs;
- a changed module that a `conftest.py` imports (a fixtures module) lists the
  directory of each conftest that imports it.

    scripts/changed_test_paths.py            # against origin/main
    scripts/changed_test_paths.py origin/dev # against another base

One entry per line. Directories carry a trailing slash; "." means the whole
suite (the repository-root conftest changed). The root conftest reads the
result from GYRINX_CHANGED_TEST_PATHS and marks matching tests `core`.
"""

import fnmatch
import pathlib
import re
import subprocess  # nosec B404 — runs one fixed git command to list changed files
import sys
from collections.abc import Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Mirrors python_files in pyproject.toml.
TEST_FILE_GLOBS = ("tests.py", "test_*.py", "*_tests.py")

SKIP_DIRS = {".venv", "node_modules", ".git", ".claude"}


def is_test_file(path: str) -> bool:
    name = pathlib.PurePosixPath(path).name
    return any(fnmatch.fnmatch(name, glob) for glob in TEST_FILE_GLOBS)


def directory_entry(path: str) -> str:
    parent = pathlib.PurePosixPath(path).parent.as_posix()
    return "." if parent == "." else parent + "/"


def module_name(path: str) -> str:
    return pathlib.PurePosixPath(path).with_suffix("").as_posix().replace("/", ".")


def find_conftests(root: pathlib.Path = ROOT) -> dict[str, str]:
    """Map each conftest's repo-relative path to its text."""
    found = {}
    for conftest in root.rglob("conftest.py"):
        rel = conftest.relative_to(root)
        if SKIP_DIRS.intersection(rel.parts):
            continue
        found[rel.as_posix()] = conftest.read_text(encoding="utf-8")
    return found


def conftests_importing(module: str, conftests: dict[str, str]) -> list[str]:
    pattern = re.compile(
        rf"^\s*(from\s+{re.escape(module)}\s+import|import\s+{re.escape(module)}\b)",
        re.MULTILINE,
    )
    return [path for path, text in conftests.items() if pattern.search(text)]


def select_changed_test_paths(
    changed_files: Iterable[str], conftests: dict[str, str]
) -> list[str]:
    """Reduce a list of changed files to the test paths that should run.

    `conftests` maps conftest paths to their source, as `find_conftests`
    returns; it is a parameter so the rule can be tested without a checkout.
    """
    entries: set[str] = set()
    for path in changed_files:
        if not path.endswith(".py"):
            continue
        if is_test_file(path):
            entries.add(path)
        elif pathlib.PurePosixPath(path).name == "conftest.py":
            entries.add(directory_entry(path))
        else:
            for conftest in conftests_importing(module_name(path), conftests):
                entries.add(directory_entry(conftest))
    if "." in entries:
        return ["."]
    return sorted(entries)


def changed_files_against(base: str) -> list[str]:
    out = subprocess.run(  # nosec B607 — fixed argv; git resolved from PATH like every repo tool
        ["git", "diff", "--name-only", "--diff-filter=AMR", f"{base}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout
    return [line for line in out.splitlines() if line and (ROOT / line).exists()]


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else "origin/main"
    changed = changed_files_against(base)
    for entry in select_changed_test_paths(changed, find_conftests()):
        print(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
