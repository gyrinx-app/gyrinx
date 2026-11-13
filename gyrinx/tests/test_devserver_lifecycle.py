"""Detached previews retain their owner and release every descendant on stop."""

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from gyrinx.devserver.processes import (
    OWNER_ENV,
    Owner,
    ProcessInspectionError,
    find_owner,
    process_start,
)
from scripts import dev_server


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result := predicate():
            return result
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for dev-server lifecycle transition")


def test_a_reused_pid_is_not_the_original_owner(monkeypatch):
    owner = Owner(1234, "Codex", "original birth")
    monkeypatch.setattr(
        "gyrinx.devserver.processes.process_start", lambda pid: "new birth"
    )
    assert not owner.alive()


def test_an_explicit_dead_owner_is_preserved_after_detachment(monkeypatch):
    owner = Owner(1234, "Codex", "birth", "thread-123")
    monkeypatch.setattr("gyrinx.devserver.processes.process_start", lambda pid: None)
    assert find_owner({OWNER_ENV: owner.encode()}, parent_pid=1) == owner
    assert not owner.alive()


@pytest.mark.parametrize("value", ["", "null", "[]", "{}", "bad json"])
def test_invalid_explicit_ownership_is_unowned(value):
    assert find_owner({OWNER_ENV: value}) is None


def test_session_identity_is_captured_before_detachment(monkeypatch):
    monkeypatch.setattr("gyrinx.devserver.processes.process_start", lambda pid: "birth")
    monkeypatch.setattr("gyrinx.devserver.processes.ps", lambda pid, columns: "claude")
    owner = find_owner(
        {"CLAUDE_PID": "1234", "CODEX_THREAD_ID": "thread-123"},
        alive=lambda pid: True,
    )
    assert owner.session_id == "thread-123"


def test_a_stale_claude_pid_cannot_adopt_an_unrelated_live_process(monkeypatch):
    monkeypatch.setattr(
        "gyrinx.devserver.processes.ps", lambda pid, columns: "/bin/sleep"
    )
    assert find_owner({"CLAUDE_PID": "1234"}, parent_pid=1) is None


@pytest.mark.parametrize("state", ["", "Z", "Z+"])
def test_missing_and_zombie_processes_are_dead(monkeypatch, state):
    monkeypatch.setattr(
        "gyrinx.devserver.processes.ps",
        lambda pid, columns: (
            f"Fri Nov 13 18:00:00 2026 {state}".strip() if state else ""
        ),
    )
    assert process_start(1234) is None


def test_denied_process_inspection_does_not_mean_the_owner_exited(monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("sandbox denied process inspection")

    monkeypatch.setattr("gyrinx.devserver.processes.subprocess.run", denied)
    with pytest.raises(ProcessInspectionError, match="Rerun with permission"):
        process_start(1234)


@pytest.mark.parametrize(
    "flags",
    [
        ["--background", "--stop"],
        ["--status", "--reset-db"],
        ["--background", "--setup-only"],
        ["--unknown"],
    ],
)
def test_invalid_lifecycle_flags_fail_before_starting_anything(flags):
    with pytest.raises(ValueError):
        dev_server.main(flags)


@pytest.fixture
def preview(tmp_path, monkeypatch):
    root = tmp_path / "preview with spaces"
    (root / "scripts").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / ".git").touch()
    # A shell, child and grandchild model dev.sh -> npm -> watcher. The
    # watcher ignores TERM so cleanup must also exercise the KILL fallback.
    (root / "scripts/dev.sh").write_text(
        '"$TEST_PYTHON" child.py &\necho "$!" > logs/child.pid\nwait\n'
    )
    (root / "child.py").write_text(
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, 'grandchild.py'])\n"
        "open('logs/grandchild.pid', 'w').write(str(child.pid))\n"
        "time.sleep(600)\n"
    )
    (root / "grandchild.py").write_text(
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "open('logs/grandchild-ready', 'w').close()\n"
        "time.sleep(600)\n"
    )
    monkeypatch.setenv("TEST_PYTHON", sys.executable)
    owner_process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(600)"]
    )
    owner = Owner(
        owner_process.pid, "Codex", process_start(owner_process.pid), "test-thread"
    )
    monkeypatch.setenv(OWNER_ENV, owner.encode())
    try:
        yield root, owner_process, owner
    finally:
        dev_server.stop(root)
        owner_process.terminate()
        owner_process.wait(timeout=5)


def launch_from_short_lived_process(root):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; from scripts.dev_server import start; "
            "import sys; sys.exit(start(Path(sys.argv[1]), [], True))",
            str(root),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return wait_for(lambda: dev_server.read_state(root))


def descendant_pids(root):
    wait_for(lambda: (root / "logs/grandchild-ready").exists())
    return [
        int((root / f"logs/{name}.pid").read_text()) for name in ("child", "grandchild")
    ]


def test_detached_preview_survives_launcher_exit_and_stop_reaps_descendants(preview):
    root, _, owner = preview
    state = launch_from_short_lived_process(root)
    pids = descendant_pids(root)
    assert dev_server.supervisor_alive(state)
    assert state["owner"] == json.loads(owner.encode())
    assert state["session_id"] == "test-thread"
    assert all(process_start(pid) for pid in pids)

    assert dev_server.stop(root) == 0
    wait_for(lambda: all(process_start(pid) is None for pid in pids))
    assert dev_server.read_state(root)["state"] == "stopped"
    assert dev_server.stop(root) == 0


def test_owner_exit_stops_the_detached_preview_and_all_descendants(preview):
    root, owner_process, _ = preview
    state = launch_from_short_lived_process(root)
    pids = descendant_pids(root)
    owner_process.terminate()
    owner_process.wait(timeout=5)
    wait_for(lambda: not dev_server.supervisor_alive(state))
    wait_for(lambda: all(process_start(pid) is None for pid in pids))
    assert "owning Codex process exited" in dev_server.read_state(root)["reason"]


def test_two_concurrent_starts_use_one_supervisor(preview):
    root, _, _ = preview
    launch_code = (
        "from pathlib import Path; from scripts.dev_server import start; "
        "import sys; sys.exit(start(Path(sys.argv[1]), [], True))"
    )
    commands = [
        subprocess.Popen(
            [sys.executable, "-c", launch_code, str(root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outputs = [command.communicate(timeout=10) for command in commands]
    assert all(command.returncode == 0 for command in commands), outputs
    assert sum("already has a dev-server supervisor" in out for out, _ in outputs) == 1
    assert dev_server.supervisor_alive(wait_for(lambda: dev_server.read_state(root)))


def test_stop_never_signals_a_pid_reused_since_the_record_was_written(preview):
    root, owner_process, owner = preview
    dev_server.write_state(
        root,
        {
            "worktree": str(root),
            "pid": owner_process.pid,
            "started": "a different birth time",
            "state": "running",
            "owner": json.loads(replace(owner, started="old birth").encode()),
        },
    )
    assert dev_server.stop(root) == 0
    assert owner_process.poll() is None


def test_foreground_supervisor_cleans_up_when_its_server_command_exits(preview):
    root, _, _ = preview
    (root / "scripts/dev.sh").write_text("exit 7\n")
    assert dev_server.start(root, [], False) == 7
    assert dev_server.read_state(root)["state"] == "stopped"


def test_stop_recovers_a_process_group_after_its_supervisor_is_killed(preview):
    root, _, _ = preview
    state = launch_from_short_lived_process(root)
    pids = descendant_pids(root)
    os.kill(state["pid"], signal.SIGKILL)
    wait_for(lambda: not dev_server.supervisor_alive(state))
    assert dev_server.group_alive(dev_server.read_state(root))
    assert dev_server.start(root, [], True) == 1
    assert dev_server.stop(root) == 0
    wait_for(lambda: all(process_start(pid) is None for pid in pids))


def test_removing_the_worktree_stops_its_process_group(preview):
    root, _, _ = preview
    state = launch_from_short_lived_process(root)
    pids = descendant_pids(root)
    (root / ".git").unlink()
    wait_for(lambda: not dev_server.supervisor_alive(state))
    wait_for(lambda: all(process_start(pid) is None for pid in pids))
    assert dev_server.read_state(root)["reason"] == "worktree removed"


def test_prune_removes_stale_records_without_stopping_reused_pids(preview, monkeypatch):
    root, owner_process, _ = preview
    dev_server.write_state(
        root, {"worktree": str(root), "pid": owner_process.pid, "started": "old"}
    )
    monkeypatch.setattr(
        dev_server.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, f"worktree {root}\n"
        ),
    )
    assert dev_server.prune(root) == 0
    assert dev_server.read_state(root) is None
    assert owner_process.poll() is None
