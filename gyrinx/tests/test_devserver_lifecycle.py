"""Detached previews retain their owner and release every descendant on stop."""

import json
import os
import shutil
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
    group_processes,
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


def only_worktree(monkeypatch, root):
    real_run = subprocess.run

    def run(args, **kwargs):
        if args == ["git", "worktree", "list", "--porcelain"]:
            return subprocess.CompletedProcess(args, 0, f"worktree {root}\n")
        return real_run(args, **kwargs)

    monkeypatch.setattr(dev_server.subprocess, "run", run)


def test_a_reused_pid_is_not_the_original_owner(monkeypatch):
    owner = Owner(1234, "Codex", "original birth")
    monkeypatch.setattr(
        "gyrinx.devserver.processes.process_start", lambda pid: "new birth"
    )
    assert not owner.alive()


def test_process_identity_survives_a_change_in_callers_timezone(monkeypatch):
    pid = os.getpid()
    monkeypatch.setenv("TZ", "UTC")
    started = process_start(pid)
    owner = Owner(pid, "Codex", started)
    for zone in ("America/New_York", "Asia/Tokyo"):
        monkeypatch.setenv("TZ", zone)
        assert owner.alive()
        member = next(
            item for item in group_processes(os.getpgid(pid)) if item["pid"] == pid
        )
        assert member["started"] == started


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
    launch_code = (
        "from pathlib import Path; from scripts.dev_server import start; "
        "import sys; sys.exit(start(Path(sys.argv[1]), [], True))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            launch_code,
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


def test_stop_refuses_startup_before_its_record_is_published(preview):
    root, _, _ = preview
    launch_code = """
from pathlib import Path
from scripts import dev_server
import sys
import time

root = Path(sys.argv[1])
original_write = dev_server.write_state
def publish(root, state):
    (root / 'logs/registration-paused').touch()
    while not (root / 'logs/registration-release').exists():
        time.sleep(0.05)
    original_write(root, state)
dev_server.write_state = publish
sys.exit(dev_server.start(root, [], False))
"""
    with (root / "logs/registration.log").open("w") as output:
        supervisor = subprocess.Popen(
            [sys.executable, "-c", launch_code, str(root)],
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_for(lambda: (root / "logs/registration-paused").exists())
            assert dev_server.read_state(root) is None
            assert dev_server.stop(root) == 1
            assert supervisor.poll() is None
            (root / "logs/registration-release").touch()
            pids = descendant_pids(root)
            assert dev_server.stop(root) == 0
            assert supervisor.wait(timeout=12) == 0
            wait_for(lambda: all(process_start(pid) is None for pid in pids))
        finally:
            (root / "logs/registration-release").touch()
            if supervisor.poll() is None:
                supervisor.terminate()
                supervisor.wait(timeout=12)


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


def test_foreground_terminal_hangup_stops_all_descendants(preview):
    root, _, _ = preview
    launch_code = (
        "from pathlib import Path; from scripts.dev_server import start; "
        "import sys; sys.exit(start(Path(sys.argv[1]), [], False))"
    )
    with (root / "logs/foreground.log").open("w") as output:
        supervisor = subprocess.Popen(
            [
                sys.executable,
                "-c",
                launch_code,
                str(root),
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            pids = descendant_pids(root)
            supervisor.send_signal(signal.SIGHUP)
            assert supervisor.wait(timeout=12) == 0
            wait_for(lambda: all(process_start(pid) is None for pid in pids))
        finally:
            if supervisor.poll() is None:
                supervisor.terminate()
                supervisor.wait(timeout=12)


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


@pytest.mark.parametrize("action", ["stop", "prune"])
def test_cleanup_recovers_survivors_after_supervisor_and_group_leader_exit(
    preview, monkeypatch, action
):
    root, _, _ = preview
    state = launch_from_short_lived_process(root)
    pids = descendant_pids(root)
    wait_for(
        lambda: any(
            member["pid"] == pids[-1]
            for member in dev_server.read_state(root).get("group_members", [])
        )
    )
    state = dev_server.read_state(root)
    os.kill(state["pid"], signal.SIGKILL)
    os.kill(state["group_pid"], signal.SIGKILL)
    wait_for(lambda: process_start(state["group_pid"]) is None)
    assert dev_server.group_alive(state)
    if action == "prune":
        only_worktree(monkeypatch, root)
    assert getattr(dev_server, action)(root) == 0
    wait_for(lambda: all(process_start(pid) is None for pid in pids))


def test_unverified_group_retains_its_record_and_reports_failed_cleanup(
    preview, monkeypatch
):
    root, _, _ = preview
    launch_from_short_lived_process(root)
    pids = descendant_pids(root)
    original = dev_server.read_state(root)
    os.kill(original["pid"], signal.SIGKILL)
    wait_for(lambda: not dev_server.supervisor_alive(original))
    unverified = {**original, "group_started": "different birth", "group_members": []}
    dev_server.write_state(root, unverified)
    only_worktree(monkeypatch, root)
    try:
        assert dev_server.stop(root) == 1
        assert dev_server.prune(root) == 1
        assert dev_server.read_state(root) == unverified
        assert all(process_start(pid) for pid in pids)
    finally:
        dev_server.write_state(root, original)


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
    only_worktree(monkeypatch, root)
    assert dev_server.prune(root) == 0
    assert dev_server.read_state(root) is None
    assert owner_process.poll() is None


def test_supervisor_exit_does_not_report_success_while_members_remain(
    tmp_path, monkeypatch
):
    (tmp_path / "logs").mkdir()
    state = {"worktree": str(tmp_path), "pid": 1234, "group_pid": 5678}
    dev_server.write_state(tmp_path, state)
    alive = iter([True, False])
    monkeypatch.setattr(dev_server, "supervisor_alive", lambda state: next(alive))
    monkeypatch.setattr(
        dev_server, "group_processes", lambda pgid: [{"pid": 5679, "started": "birth"}]
    )
    signals = []
    monkeypatch.setattr(
        dev_server.os, "kill", lambda pid, sig: signals.append((pid, sig))
    )
    assert dev_server.stop(tmp_path) == 1
    assert signals == [(1234, signal.SIGTERM)]
    assert dev_server.read_state(tmp_path) == state


@pytest.mark.parametrize("action", ["--background", "--status", "--stop"])
def test_old_bootstrap_python_uses_uv_without_project_dependencies(tmp_path, action):
    root = tmp_path / "bootstrap with spaces"
    (root / "scripts/lib").mkdir(parents=True)
    (root / "bin").mkdir()
    shutil.copy2(dev_server.ROOT / "scripts/dev.sh", root / "scripts/dev.sh")
    (root / ".python-version").write_text("3.14.6\n")
    (root / "scripts/lib/worktree.sh").write_text(
        'worktree_python() { printf "%s\\n" "$FAKE_BOOTSTRAP_PYTHON"; }\n'
    )
    old_python = root / "bin/old-python"
    old_python.write_text("#!/bin/sh\nexit 1\n")
    old_python.chmod(0o755)
    uv = root / "bin/uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$UV_ARGS_FILE"\n')
    uv.chmod(0o755)
    args_file = root / "uv-args"
    result = subprocess.run(
        ["/bin/bash", str(root / "scripts/dev.sh"), action],
        env={
            **os.environ,
            "PATH": f"{root / 'bin'}:{os.environ['PATH']}",
            "FAKE_BOOTSTRAP_PYTHON": str(old_python),
            "UV_ARGS_FILE": str(args_file),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert args_file.read_text().splitlines() == [
        "run",
        "--no-project",
        "--python",
        "3.14.6",
        str(root / "scripts/dev_server.py"),
        action,
    ]
