"""Force provisioning lock initialization, recovery and release interleavings."""

import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.core
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["frontend", "venv"])
def provisioner(tmp_path, request):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    for name in ("package.json", "package-lock.json", "uv.lock", "pyproject.toml"):
        (worktree / name).write_text("{}\n")
    (worktree / "vite.config.mts").touch()
    (worktree / "n26/frontend").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    installer = """#!/bin/bash
set -eu
printf '%s\\n' "$*" >> "$CALL_LOG"
if [ "$1" = ci ]; then
  mkdir -p node_modules
elif [ "$1" = run ]; then
  mkdir -p n26/core/static/n26/react
  echo '{}' > n26/core/static/n26/react/manifest.json
else
  mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
  touch "$UV_PROJECT_ENVIRONMENT/bin/activate"
  printf '#!/bin/bash\\nexit 0\\n' > "$UV_PROJECT_ENVIRONMENT/bin/python"
  chmod +x "$UV_PROJECT_ENVIRONMENT/bin/python"
fi
"""
    for name in ("npm", "uv"):
        tool = bin_dir / name
        tool.write_text(installer)
        tool.chmod(0o755)
    python = bin_dir / "python"
    python.write_text("#!/bin/bash\nexit 0\n")
    python.chmod(0o755)
    lock = worktree / f".gyrinx-{request.param}-provision.lock"
    call_log = tmp_path / "calls"
    processes = []

    def start(*, pause=""):
        process = subprocess.Popen(
            [
                "/bin/bash",
                "-eu",
                "-c",
                """
source "$1"
pause_owner() {
  touch "$PAUSED"
  while [ ! -f "$RESUME" ]; do command sleep 0.01; done
}
mkdir() {
  command mkdir "$@" || return
  if [ "${PAUSE:-}" = initialization ] && [ "$*" = "$LOCK" ]; then
    pause_owner
  fi
}
_provision_lock_handoff_hook() {
  if [ "${PAUSE:-}" = release ]; then pause_owner; fi
}
touch "$STARTED"
"$2" "$3"
if [ "${PAUSE:-}" = after ]; then pause_owner; fi
""",
                "test",
                str(REPO_ROOT / "scripts/lib/worktree.sh"),
                f"provision_worktree_{request.param}",
                str(worktree),
            ],
            env=os.environ
            | {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "CALL_LOG": str(call_log),
                "LOCK": str(lock),
                "PAUSE": pause,
                "PAUSED": str(tmp_path / "paused"),
                "RESUME": str(tmp_path / "resume"),
                "STARTED": str(tmp_path / f"started-{len(processes)}"),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        processes.append(process)
        return process

    yield worktree, lock, call_log, start
    (tmp_path / "resume").touch()
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=10)


def _wait_for(path):
    deadline = time.monotonic() + 10
    while not path.exists():
        assert time.monotonic() < deadline, f"Timed out waiting for {path}"
        time.sleep(0.01)


def _succeeded(process):
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, stdout + stderr


@pytest.mark.parametrize("pause", ["initialization", "release"])
def test_live_owner_cannot_lose_its_lock_without_a_pid(provisioner, tmp_path, pause):
    _, lock, call_log, start = provisioner
    owner = start(pause=pause)
    _wait_for(tmp_path / "paused")
    assert not (lock / "pid").exists()
    waiter = start()
    _wait_for(tmp_path / "started-1")

    # The directory has no PID, but the shell must still hold the kernel lock.
    # Checking it directly makes the regression independent of scheduling.
    with Path(f"{lock}.guard").open("a") as guard:
        with pytest.raises(BlockingIOError):
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if pause == "initialization":
        with pytest.raises(subprocess.TimeoutExpired):
            waiter.communicate(timeout=1.2)
    (tmp_path / "resume").touch()
    _succeeded(owner)
    _succeeded(waiter)
    calls = call_log.read_text().splitlines()
    assert calls == (
        ["ci --no-audit --no-fund", "run js"]
        if "frontend" in lock.name
        else ["sync --locked --quiet"]
    )
    assert not lock.exists()


def test_killed_initializing_owner_does_not_block_recovery(provisioner, tmp_path):
    _, lock, call_log, start = provisioner
    owner = start(pause="initialization")
    _wait_for(tmp_path / "paused")
    os.killpg(owner.pid, signal.SIGKILL)
    owner.communicate(timeout=10)

    _succeeded(start())

    assert not lock.exists()
    assert len(call_log.read_text().splitlines()) == (
        2 if "frontend" in lock.name else 1
    )


@pytest.mark.parametrize("owner_alive", [False, True])
def test_concurrent_waiters_recover_an_abandoned_lock_only_once(
    provisioner, owner_alive
):
    _, lock, call_log, start = provisioner
    lock.mkdir()
    stale_pid = os.getpid() if owner_alive else 99999999
    (lock / "pid").write_text(f"{stale_pid}\n")

    waiters = [start() for _ in range(4)]
    for waiter in waiters:
        _succeeded(waiter)

    assert not lock.exists()
    assert len(call_log.read_text().splitlines()) == (
        2 if "frontend" in lock.name else 1
    )


def test_provisioner_releases_guard_while_calling_shell_stays_alive(
    provisioner, tmp_path
):
    _, lock, _, start = provisioner
    caller = start(pause="after")
    _wait_for(tmp_path / "paused")

    with Path(f"{lock}.guard").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)

    (tmp_path / "resume").touch()
    _succeeded(caller)


def test_guard_timeout_preserves_the_live_owner(tmp_path):
    guard = tmp_path / "guard"
    with guard.open("a") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX)
        result = subprocess.run(
            [
                "/bin/bash",
                "-c",
                'exec 9>> "$1"; "$2" -c "$3"',
                "test",
                str(guard),
                sys.executable,
                "from scripts.lib.provision_lock import acquire; "
                "raise SystemExit(acquire('test lock', timeout=0.1))",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "Timed out waiting for the test lock" in result.stderr
        with guard.open("a") as waiter:
            with pytest.raises(BlockingIOError):
                fcntl.flock(waiter, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_guard_without_an_inherited_descriptor_fails():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/lib/provision_lock.py"), "test lock"],
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "Could not acquire the test lock" in result.stderr
