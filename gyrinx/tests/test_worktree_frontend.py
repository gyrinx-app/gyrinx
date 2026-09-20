"""Exercise React-asset recovery in scripts/lib/worktree.sh."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_fake_npm(bin_dir: Path) -> None:
    npm = bin_dir / "npm"
    npm.write_text(
        """#!/bin/bash
set -eu
printf '%s\\n' "$*" >> "$NPM_CALL_LOG"
printf 'PATH=%s\\n' "$PATH" >> "$NPM_PATH_LOG"
if [ -n "${NPM_DELAY:-}" ]; then
  sleep "$NPM_DELAY"
fi
if [ "${NPM_STATUS:-0}" -ne 0 ]; then
  exit "$NPM_STATUS"
fi
if [ "$1" = "ci" ]; then
  mkdir -p node_modules
elif [ "$1" = "run" ] && [ "$2" = "js" ]; then
  mkdir -p n26/core/static/n26/react
  printf '{}\\n' > n26/core/static/n26/react/manifest.json
fi
"""
    )
    npm.chmod(0o755)


def _write_worktree_venv(worktree: Path) -> Path:
    python = worktree / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/bash\nexit 0\n")
    python.chmod(0o755)
    return python


def _path_with_bin(bin_dir: Path, *, hide_npm=False) -> str:
    parts = [str(bin_dir)]
    for part in os.environ.get("PATH", "").split(":"):
        if hide_npm and (Path(part) / "npm").exists():
            continue
        parts.append(part)
    return ":".join(parts)


def _provision(worktree: Path, bin_dir: Path, *, hide_npm=False, **extra_env):
    return subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1" && provision_worktree_frontend "$2"',
            "test",
            str(REPO_ROOT / "scripts/lib/worktree.sh"),
            str(worktree),
        ],
        text=True,
        capture_output=True,
        env=os.environ
        | {
            "PATH": _path_with_bin(bin_dir, hide_npm=hide_npm),
            "NPM_CALL_LOG": str(bin_dir / "npm-calls"),
            "NPM_PATH_LOG": str(bin_dir / "npm-path"),
        }
        | extra_env,
    )


def _touch_later(*paths: Path) -> None:
    later = time.time() + 10
    for path in paths:
        os.utime(path, (later, later))


def _islands_worktree(tmp_path: Path) -> Path:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "package.json").write_text("{}\n")
    (worktree / "package-lock.json").write_text("{}\n")
    (worktree / "vite.config.mts").write_text("export default {}\n")
    (worktree / "n26/frontend/islands").mkdir(parents=True)
    (worktree / "n26/frontend/islands/list.tsx").write_text("export {}\n")
    _write_worktree_venv(worktree)
    return worktree


def test_frontend_provision_skips_a_checkout_without_vite(tmp_path):
    worktree = tmp_path / "worktree"
    bin_dir = tmp_path / "bin"
    worktree.mkdir()
    bin_dir.mkdir()
    _write_fake_npm(bin_dir)
    (worktree / "package.json").write_text("{}\n")

    result = _provision(worktree, bin_dir)

    assert result.returncode == 0, result.stderr
    assert not (bin_dir / "npm-calls").exists()


def test_frontend_provision_installs_and_builds_once(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_npm(bin_dir)

    first = _provision(worktree, bin_dir)
    unchanged = _provision(worktree, bin_dir)

    assert first.returncode == 0, first.stderr
    assert unchanged.returncode == 0, unchanged.stderr
    assert (bin_dir / "npm-calls").read_text().splitlines() == [
        "ci --no-audit --no-fund",
        "run js",
    ]
    assert str(worktree / ".venv/bin") in (bin_dir / "npm-path").read_text()
    assert "npm audit fix" not in (bin_dir / "npm-calls").read_text()


def test_frontend_provision_reinstalls_after_the_lockfile_changes(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_npm(bin_dir)
    assert _provision(worktree, bin_dir).returncode == 0
    (worktree / "package-lock.json").write_text('{"lockfileVersion": 2}\n')
    _touch_later(worktree / "package-lock.json")

    changed = _provision(worktree, bin_dir)

    assert changed.returncode == 0, changed.stderr
    assert (bin_dir / "npm-calls").read_text().splitlines() == [
        "ci --no-audit --no-fund",
        "run js",
        "ci --no-audit --no-fund",
        "run js",
    ]


def test_frontend_provision_rebuilds_when_island_sources_change(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_npm(bin_dir)
    assert _provision(worktree, bin_dir).returncode == 0
    (worktree / "n26/frontend/islands/list.tsx").write_text(
        "export const changed = 1\n"
    )
    _touch_later(worktree / "n26/frontend/islands/list.tsx")

    changed = _provision(worktree, bin_dir)

    assert changed.returncode == 0, changed.stderr
    assert (bin_dir / "npm-calls").read_text().splitlines() == [
        "ci --no-audit --no-fund",
        "run js",
        "run js",
    ]


def test_frontend_provision_ignores_generated_frontend_output(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_npm(bin_dir)
    assert _provision(worktree, bin_dir).returncode == 0
    generated = worktree / "n26/frontend/generated/cotton.json"
    generated.parent.mkdir(parents=True)
    generated.write_text("{}\n")
    _touch_later(generated)

    result = _provision(worktree, bin_dir)

    assert result.returncode == 0, result.stderr
    assert (bin_dir / "npm-calls").read_text().splitlines() == [
        "ci --no-audit --no-fund",
        "run js",
    ]


def test_missing_npm_fails_with_the_manual_rebuild_commands(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    result = _provision(worktree, bin_dir, hide_npm=True)

    assert result.returncode == 1
    assert "npm is not on PATH" in result.stderr
    assert "npm ci --no-audit --no-fund" in result.stderr
    assert "npm run js" in result.stderr


def test_failed_npm_ci_mentions_not_to_audit_fix(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_npm(bin_dir)

    result = _provision(worktree, bin_dir, NPM_STATUS="7")

    assert result.returncode == 1
    assert "npm ci failed" in result.stderr
    assert "npm audit fix" in result.stderr


def test_frontend_provision_rebuilds_when_cotton_templates_change(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_npm(bin_dir)
    assert _provision(worktree, bin_dir).returncode == 0
    cotton = worktree / "n26/core/templates/cotton/n26/search_bar.html"
    cotton.parent.mkdir(parents=True)
    cotton.write_text("<div></div>\n")
    _touch_later(cotton)

    changed = _provision(worktree, bin_dir)

    assert changed.returncode == 0, changed.stderr
    assert (bin_dir / "npm-calls").read_text().splitlines() == [
        "ci --no-audit --no-fund",
        "run js",
        "run js",
    ]


def test_frontend_provision_rebuilds_when_icon_sources_change(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_npm(bin_dir)
    assert _provision(worktree, bin_dir).returncode == 0
    icons = worktree / "n26/core/icons.py"
    icons.parent.mkdir(parents=True, exist_ok=True)
    icons.write_text("def resolve(name):\n    return name\n")
    _touch_later(icons)

    changed = _provision(worktree, bin_dir)

    assert changed.returncode == 0, changed.stderr
    assert (bin_dir / "npm-calls").read_text().splitlines()[-1] == "run js"
    assert (bin_dir / "npm-calls").read_text().count("ci --no-audit") == 1


def test_concurrent_frontend_provisioners_only_install_once(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_npm(bin_dir)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: _provision(worktree, bin_dir, NPM_DELAY="1"),
                range(2),
            )
        )

    assert all(result.returncode == 0 for result in results), [
        result.stderr for result in results
    ]
    assert (bin_dir / "npm-calls").read_text().splitlines() == [
        "ci --no-audit --no-fund",
        "run js",
    ]


def test_frontend_provisioner_recovers_an_abandoned_empty_lock(tmp_path):
    worktree = _islands_worktree(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (worktree / ".gyrinx-frontend-provision.lock").mkdir()
    _write_fake_npm(bin_dir)

    result = _provision(worktree, bin_dir)

    assert result.returncode == 0, result.stderr
    assert not (worktree / ".gyrinx-frontend-provision.lock").exists()
    assert (bin_dir / "npm-calls").read_text().splitlines() == [
        "ci --no-audit --no-fund",
        "run js",
    ]


def test_codex_run_uses_the_shared_frontend_provisioner():
    run = (REPO_ROOT / ".codex/run.sh").read_text()

    assert 'provision_worktree_frontend "$PROJECT_DIR"' in run
    assert "npm audit fix" not in run
