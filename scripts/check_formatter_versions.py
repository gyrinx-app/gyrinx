#!/usr/bin/env python3
"""Keep local, locked, and pre-commit formatter versions in agreement."""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMATTERS = ("djlint", "ruff")
PRE_COMMIT_REPOSITORIES = {
    "https://github.com/djlint/djlint": "djlint",
    "https://github.com/astral-sh/ruff-pre-commit": "ruff",
}


def locked_versions(lock_path: Path) -> dict[str, str]:
    """Return formatter versions from uv.lock."""
    with lock_path.open("rb") as lock_file:
        packages = tomllib.load(lock_file)["package"]
    versions = {
        package["name"].lower(): package["version"]
        for package in packages
        if package["name"].lower() in FORMATTERS
    }
    missing = set(FORMATTERS) - versions.keys()
    if missing:
        raise ValueError(f"uv.lock does not pin: {', '.join(sorted(missing))}")
    return versions


def pre_commit_versions(config_path: Path) -> dict[str, str]:
    """Return formatter versions from the relevant pre-commit repository revs."""
    versions: dict[str, str] = {}
    repository: str | None = None
    for line in config_path.read_text().splitlines():
        if match := re.match(r"\s*-\s+repo:\s*[\"']?([^\"'#\s]+)", line):
            repository = match.group(1).removesuffix(".git").lower()
            continue
        if repository not in PRE_COMMIT_REPOSITORIES:
            continue
        if match := re.match(r"\s+rev:\s*[\"']?([^\"'#\s]+)", line):
            formatter = PRE_COMMIT_REPOSITORIES[repository]
            versions[formatter] = match.group(1).removeprefix("v")
            repository = None

    missing = set(FORMATTERS) - versions.keys()
    if missing:
        raise ValueError(
            ".pre-commit-config.yaml does not pin: " + ", ".join(sorted(missing))
        )
    return versions


def installed_versions() -> dict[str, str | None]:
    """Return versions installed in the Python environment running this script."""
    versions: dict[str, str | None] = {}
    for formatter in FORMATTERS:
        try:
            versions[formatter] = importlib.metadata.version(formatter)
        except importlib.metadata.PackageNotFoundError:
            versions[formatter] = None
    return versions


def mismatches(
    expected: Mapping[str, str], actual: Mapping[str, str | None]
) -> list[tuple[str, str, str | None]]:
    """Return (name, expected, actual) for versions that differ."""
    return [
        (formatter, expected[formatter], actual.get(formatter))
        for formatter in FORMATTERS
        if actual.get(formatter) != expected[formatter]
    ]


def _print_mismatches(
    heading: str,
    differences: list[tuple[str, str, str | None]],
    actual_label: str,
) -> None:
    print(heading, file=sys.stderr)
    for formatter, expected, actual in differences:
        print(
            f"  {formatter}: uv.lock has {expected}; "
            f"{actual_label} has {actual or 'not installed'}",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="only compare uv.lock with .pre-commit-config.yaml",
    )
    args = parser.parse_args(argv)

    try:
        locked = locked_versions(REPO_ROOT / "uv.lock")
        configured = pre_commit_versions(REPO_ROOT / ".pre-commit-config.yaml")
    except (KeyError, OSError, tomllib.TOMLDecodeError, ValueError) as error:
        print(f"ERROR: Cannot check formatter versions: {error}", file=sys.stderr)
        return 1

    failed = False
    if differences := mismatches(locked, configured):
        _print_mismatches(
            "ERROR: Formatter pins in pre-commit disagree with uv.lock:",
            differences,
            ".pre-commit-config.yaml",
        )
        print("Update both pins together before running formatters.", file=sys.stderr)
        failed = True

    if not args.config_only and (
        differences := mismatches(locked, installed_versions())
    ):
        _print_mismatches(
            "ERROR: Installed formatter versions disagree with uv.lock:",
            differences,
            "the active environment",
        )
        print("Run `uv sync --locked` and try again.", file=sys.stderr)
        failed = True

    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
