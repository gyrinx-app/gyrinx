"""Checks for the formatter-version guard used by local tooling and CI."""

import re
from importlib import metadata

import pytest

from scripts.check_formatter_versions import (
    FORMATTERS,
    REPO_ROOT,
    installed_versions,
    locked_versions,
    mismatches,
    pre_commit_versions,
)

pytestmark = pytest.mark.core


def test_repository_formatter_pins_match():
    locked = locked_versions(REPO_ROOT / "uv.lock")
    configured = pre_commit_versions(REPO_ROOT / ".pre-commit-config.yaml")

    assert not mismatches(locked, configured)


def test_pre_commit_stops_before_running_a_mismatched_formatter():
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text()
    guard_position = config.index("id: check-formatter-versions")

    assert "fail_fast: true" in config
    assert guard_position < config.index("repo: https://github.com/djlint/djLint")
    assert guard_position < config.index(
        "repo: https://github.com/astral-sh/ruff-pre-commit"
    )


def test_dependabot_groups_only_formatter_updates_across_ecosystems():
    config = (REPO_ROOT / ".github/dependabot.yml").read_text()
    blocks = re.findall(
        r"^  - package-ecosystem:.*?(?=^  - package-ecosystem:|\Z)",
        config,
        flags=re.MULTILINE | re.DOTALL,
    )

    for ecosystem, patterns in {
        "uv": ('      - "djlint"', '      - "ruff"'),
        "pre-commit": ('      - "*djlint*"', '      - "*ruff*"'),
    }.items():
        entries = [
            block for block in blocks if f'"{ecosystem}"' in block.splitlines()[0]
        ]
        regular = [block for block in entries if "multi-ecosystem-group" not in block]
        grouped = [block for block in entries if "multi-ecosystem-group" in block]

        assert len(regular) == 1
        assert len(grouped) == 1
        assert all(pattern in grouped[0] for pattern in patterns)
        assert all(
            pattern.replace('      - "', '      - dependency-name: "') in regular[0]
            for pattern in patterns
        )


def test_active_test_environment_matches_the_lock():
    locked = locked_versions(REPO_ROOT / "uv.lock")

    assert not mismatches(locked, installed_versions())


def test_locked_versions_reads_only_the_formatters(tmp_path):
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        """
[[package]]
name = "djlint"
version = "1.2.3"

[[package]]
name = "unrelated"
version = "9.9.9"

[[package]]
name = "ruff"
version = "4.5.6"
""".lstrip()
    )

    assert locked_versions(lock_path) == {"djlint": "1.2.3", "ruff": "4.5.6"}


def test_pre_commit_versions_normalises_repository_and_tag_names(tmp_path):
    config_path = tmp_path / ".pre-commit-config.yaml"
    config_path.write_text(
        """
repos:
  - repo: https://github.com/djlint/djLint.git
    rev: v1.2.3
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v4.5.6
""".lstrip()
    )

    assert pre_commit_versions(config_path) == {
        "djlint": "1.2.3",
        "ruff": "4.5.6",
    }


def test_installed_versions_reports_a_missing_formatter(monkeypatch):
    real_version = metadata.version

    def fake_version(distribution_name):
        if distribution_name == "djlint":
            raise metadata.PackageNotFoundError
        return real_version(distribution_name)

    monkeypatch.setattr(metadata, "version", fake_version)

    versions = installed_versions()

    assert versions["djlint"] is None
    assert set(versions) == set(FORMATTERS)


def test_mismatches_reports_missing_and_different_versions():
    assert mismatches(
        {"djlint": "1.46.1", "ruff": "0.16.6"},
        {"djlint": "1.44.2", "ruff": None},
    ) == [
        ("djlint", "1.46.1", "1.44.2"),
        ("ruff", "0.16.6", None),
    ]
