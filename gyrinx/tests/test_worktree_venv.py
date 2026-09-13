"""Exercise the uv.lock stamp in scripts/lib/worktree.sh."""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_fake_uv(bin_dir: Path) -> None:
    uv = bin_dir / "uv"
    uv.write_text(
        """#!/bin/bash
set -eu
printf 'sync\\n' >> "$UV_CALL_LOG"
if [ "${UV_STATUS:-0}" -ne 0 ]; then
  exit "$UV_STATUS"
fi
mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
touch "$UV_PROJECT_ENVIRONMENT/bin/activate"
"""
    )
    uv.chmod(0o755)


def _provision(worktree: Path, bin_dir: Path, call_log: Path, **extra_env):
    return subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1" && provision_worktree_venv "$2"',
            "test",
            str(REPO_ROOT / "scripts/lib/worktree.sh"),
            str(worktree),
        ],
        text=True,
        capture_output=True,
        env=os.environ
        | {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "UV_CALL_LOG": str(call_log),
        }
        | extra_env,
    )


def test_provision_syncs_once_then_only_after_the_lock_changes(tmp_path):
    worktree = tmp_path / "worktree"
    bin_dir = tmp_path / "bin"
    call_log = tmp_path / "uv-calls"
    worktree.mkdir()
    bin_dir.mkdir()
    _write_fake_uv(bin_dir)
    lock_file = worktree / "uv.lock"
    lock_file.write_text("version = 1\n")

    first = _provision(worktree, bin_dir, call_log)
    unchanged = _provision(worktree, bin_dir, call_log)
    lock_file.write_text("version = 2\n")
    changed = _provision(worktree, bin_dir, call_log)

    assert first.returncode == 0, first.stderr
    assert unchanged.returncode == 0, unchanged.stderr
    assert changed.returncode == 0, changed.stderr
    assert call_log.read_text().splitlines() == ["sync", "sync"]
    assert "uv.lock changed" in changed.stderr


def test_failed_resync_preserves_the_venv_and_retries(tmp_path):
    worktree = tmp_path / "worktree"
    bin_dir = tmp_path / "bin"
    call_log = tmp_path / "uv-calls"
    worktree.mkdir()
    bin_dir.mkdir()
    _write_fake_uv(bin_dir)
    lock_file = worktree / "uv.lock"
    lock_file.write_text("version = 1\n")
    assert _provision(worktree, bin_dir, call_log).returncode == 0
    old_stamp = (worktree / ".venv/.gyrinx-uv-lock.sha256").read_text()
    lock_file.write_text("version = 2\n")

    failed = _provision(worktree, bin_dir, call_log, UV_STATUS="7")

    assert failed.returncode == 1
    assert (worktree / ".venv").is_dir()
    assert (worktree / ".venv/.gyrinx-uv-lock.sha256").read_text() == old_stamp
    retried = _provision(worktree, bin_dir, call_log)
    assert retried.returncode == 0, retried.stderr
    assert call_log.read_text().splitlines() == ["sync", "sync", "sync"]
