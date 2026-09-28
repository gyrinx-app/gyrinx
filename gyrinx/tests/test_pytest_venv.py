"""A sibling worktree's pytest on PATH imports that checkout's code.

wren hit this on #lessons (27 Sep): bare ``pytest`` resolved to another
worktree's ``.venv`` and produced phantom failures. The root conftest
refuses to start in that case.
"""

import sys
from pathlib import Path

import pytest

from gyrinx.pytest_venv import foreign_venv_message

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[2]


def _python(root: Path) -> Path:
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    return python


def test_this_worktree_venv_is_silent(tmp_path):
    worktree = tmp_path / "here"
    python = _python(worktree)

    assert foreign_venv_message(worktree, python) is None


def test_a_sibling_worktree_venv_is_an_error(tmp_path):
    here = tmp_path / "here"
    other = tmp_path / "other"
    _python(here)
    other_python = _python(other)

    message = foreign_venv_message(here, other_python)

    assert message is not None
    assert str(other_python.resolve()) in message
    expected = str((here / ".venv" / "bin" / "python").resolve())
    assert expected in message
    assert f"{expected} -m pytest" in message
    assert "sibling" in message


def test_system_python_is_silent_even_when_a_venv_exists(tmp_path):
    worktree = tmp_path / "here"
    _python(worktree)
    system = tmp_path / "usr" / "bin" / "python3"
    system.parent.mkdir(parents=True)
    system.write_text("#!/bin/sh\n")
    system.chmod(0o755)

    assert foreign_venv_message(worktree, system) is None


def test_no_local_venv_means_nothing_to_mismatch(tmp_path):
    worktree = tmp_path / "here"
    worktree.mkdir()
    other_python = _python(tmp_path / "other")

    assert foreign_venv_message(worktree, other_python) is None


def test_a_venv_directory_name_that_is_not_dot_venv_is_silent(tmp_path):
    worktree = tmp_path / "here"
    worktree.mkdir()
    (worktree / ".venv").mkdir()
    other = tmp_path / "other" / "venv" / "bin" / "python"
    other.parent.mkdir(parents=True)
    other.write_text("#!/bin/sh\n")
    other.chmod(0o755)

    assert foreign_venv_message(worktree, other) is None


def test_this_session_uses_this_worktree_or_is_not_a_venv():
    assert foreign_venv_message(ROOT, sys.executable) is None
