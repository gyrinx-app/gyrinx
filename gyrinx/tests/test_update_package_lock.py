"""npm 10 can leave a nested dependency after an overrides change.

``./scripts/update_package_lock.sh`` rewrites ``package-lock.json`` with npm 11.
``--check`` runs ``npm ls --package-lock-only`` and does not rewrite the file.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "update_package_lock.sh"
LOCK = ROOT / "package-lock.json"


def _fake_npm(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "npm"
    path.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        '  if [ "${FAKE_NPM_MISSING:-}" = "1" ]; then\n'
        "    exit 127\n"
        "  fi\n"
        '  printf "%s\\n" "${FAKE_NPM_VERSION:?}"\n'
        "  exit 0\n"
        "fi\n"
        'printf "%s\\n" "$*" >> "${FAKE_NPM_LOG:?}"\n'
        'exit "${FAKE_NPM_EXIT:-0}"\n',
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _run(tmp_path, *args, version="10.9.2", exit_code="0", missing=False):
    log = tmp_path / "npm.log"
    bin_dir = tmp_path / "bin"
    _fake_npm(bin_dir)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_NPM_LOG"] = str(log)
    env["FAKE_NPM_EXIT"] = exit_code
    env["FAKE_NPM_VERSION"] = version
    if missing:
        env["FAKE_NPM_MISSING"] = "1"
    result = subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    recorded = log.read_text(encoding="utf-8") if log.exists() else ""
    return result, recorded


def test_npm_10_update_dry_run_selects_npm_11(tmp_path):
    result, recorded = _run(tmp_path, "--dry-run", version="10.9.2")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "npx --yes npm@11 install --package-lock-only --ignore-scripts --no-audit --no-fund",
        "npx --yes npm@11 ls --package-lock-only",
    ]
    assert recorded == ""


def test_npm_11_update_dry_run_uses_local_npm(tmp_path):
    result, recorded = _run(tmp_path, "--dry-run", version="11.6.2")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "npm install --package-lock-only --ignore-scripts --no-audit --no-fund",
        "npm ls --package-lock-only",
    ]
    assert recorded == ""


def test_npm_10_check_uses_local_npm_ls(tmp_path):
    result, recorded = _run(tmp_path, "--check", "--dry-run", version="10.9.2")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["npm ls --package-lock-only"]
    assert recorded == ""


def test_missing_npm_check_uses_npm_11(tmp_path):
    result, recorded = _run(tmp_path, "--check", "--dry-run", missing=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["npx --yes npm@11 ls --package-lock-only"]
    assert recorded == ""


def test_check_failure_names_the_regeneration_command(tmp_path):
    before = LOCK.read_bytes()
    result, recorded = _run(tmp_path, "--check", version="10.9.2", exit_code="1")
    assert result.returncode == 1
    assert "package-lock.json does not satisfy package.json overrides." in result.stderr
    assert "./scripts/update_package_lock.sh" in result.stderr
    assert recorded == "ls --package-lock-only\n"
    assert LOCK.read_bytes() == before


def test_unknown_argument_exits_2(tmp_path):
    result, recorded = _run(tmp_path, "--apply", version="11.0.0")
    assert result.returncode == 2
    assert "Unknown argument: --apply" in result.stderr
    assert recorded == ""


def test_repository_lockfile_satisfies_overrides():
    before = LOCK.read_bytes()
    result = subprocess.run(
        [str(SCRIPT), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert LOCK.read_bytes() == before
