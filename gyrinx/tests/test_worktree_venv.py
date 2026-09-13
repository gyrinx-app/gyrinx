"""Exercise the dependency-input stamp in scripts/lib/worktree.sh."""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
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
if [ -n "${UV_DELAY:-}" ]; then
  sleep "$UV_DELAY"
fi
mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
touch "$UV_PROJECT_ENVIRONMENT/bin/activate"
"""
    )
    uv.chmod(0o755)


def _write_failing_sha256sum(bin_dir: Path) -> None:
    sha256sum = bin_dir / "sha256sum"
    sha256sum.write_text("#!/bin/bash\nexit 7\n")
    sha256sum.chmod(0o755)


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


def test_provision_syncs_once_then_after_dependency_inputs_change(tmp_path):
    worktree = tmp_path / "worktree"
    bin_dir = tmp_path / "bin"
    call_log = tmp_path / "uv-calls"
    worktree.mkdir()
    bin_dir.mkdir()
    _write_fake_uv(bin_dir)
    lock_file = worktree / "uv.lock"
    lock_file.write_text("version = 1\n")
    project_file = worktree / "pyproject.toml"
    project_file.write_text("[project]\nname = 'test'\n")

    first = _provision(worktree, bin_dir, call_log)
    unchanged = _provision(worktree, bin_dir, call_log)
    project_file.write_text("[project]\nname = 'changed'\n")
    project_changed = _provision(worktree, bin_dir, call_log)
    lock_file.write_text("version = 2\n")
    lock_changed = _provision(worktree, bin_dir, call_log)

    assert first.returncode == 0, first.stderr
    assert unchanged.returncode == 0, unchanged.stderr
    assert project_changed.returncode == 0, project_changed.stderr
    assert lock_changed.returncode == 0, lock_changed.stderr
    assert call_log.read_text().splitlines() == ["sync", "sync", "sync"]
    assert "dependency inputs changed" in project_changed.stderr
    assert "dependency inputs changed" in lock_changed.stderr


def test_failed_resync_preserves_the_venv_and_retries(tmp_path):
    worktree = tmp_path / "worktree"
    bin_dir = tmp_path / "bin"
    call_log = tmp_path / "uv-calls"
    worktree.mkdir()
    bin_dir.mkdir()
    _write_fake_uv(bin_dir)
    lock_file = worktree / "uv.lock"
    lock_file.write_text("version = 1\n")
    (worktree / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    assert _provision(worktree, bin_dir, call_log).returncode == 0
    old_stamp = (worktree / ".venv/.gyrinx-uv-inputs").read_text()
    lock_file.write_text("version = 2\n")

    failed = _provision(worktree, bin_dir, call_log, UV_STATUS="7")

    assert failed.returncode == 1
    assert (worktree / ".venv").is_dir()
    assert (worktree / ".venv/.gyrinx-uv-inputs").read_text() == old_stamp
    retried = _provision(worktree, bin_dir, call_log)
    assert retried.returncode == 0, retried.stderr
    assert call_log.read_text().splitlines() == ["sync", "sync", "sync"]


def test_hash_failure_never_treats_an_existing_venv_as_current(tmp_path):
    worktree = tmp_path / "worktree"
    bin_dir = tmp_path / "bin"
    call_log = tmp_path / "uv-calls"
    worktree.mkdir()
    bin_dir.mkdir()
    (worktree / "uv.lock").write_text("version = 1\n")
    (worktree / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (worktree / ".venv").mkdir()
    (worktree / ".venv/.gyrinx-uv-inputs").write_text("")
    _write_fake_uv(bin_dir)
    _write_failing_sha256sum(bin_dir)

    result = _provision(worktree, bin_dir, call_log)

    assert result.returncode == 1
    assert "Could not hash" in result.stderr
    assert not call_log.exists()


def test_stamp_write_failure_leaves_the_environment_unverified(tmp_path):
    worktree = tmp_path / "worktree"
    bin_dir = tmp_path / "bin"
    call_log = tmp_path / "uv-calls"
    worktree.mkdir()
    bin_dir.mkdir()
    (worktree / "uv.lock").write_text("version = 1\n")
    (worktree / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (worktree / ".venv/.gyrinx-uv-inputs").mkdir(parents=True)
    _write_fake_uv(bin_dir)

    result = _provision(worktree, bin_dir, call_log)

    assert result.returncode == 1
    assert "Could not record dependency state" in result.stderr
    assert call_log.read_text().splitlines() == ["sync"]


def test_web_setup_uses_the_shared_stamped_provisioner():
    setup = (REPO_ROOT / "scripts/setup_web.sh").read_text()

    assert 'provision_worktree_venv "$PROJECT_DIR"' in setup
    assert "UV_PROJECT_ENVIRONMENT=.venv uv sync --locked" not in setup


def test_concurrent_provisioners_only_sync_once(tmp_path):
    worktree = tmp_path / "worktree"
    bin_dir = tmp_path / "bin"
    call_log = tmp_path / "uv-calls"
    worktree.mkdir()
    bin_dir.mkdir()
    (worktree / "uv.lock").write_text("version = 1\n")
    (worktree / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    _write_fake_uv(bin_dir)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: _provision(worktree, bin_dir, call_log, UV_DELAY="1"),
                range(2),
            )
        )

    assert all(result.returncode == 0 for result in results)
    assert call_log.read_text().splitlines() == ["sync"]
