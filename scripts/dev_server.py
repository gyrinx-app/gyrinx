"""Own the complete dev.sh process group, including detached previews.

This entry point uses only the standard library so status and stop also work
before provisioning a worktree's virtualenv.
"""

import fcntl
import json
import os
import signal
import socket
import subprocess  # nosec B404 — local dev.sh and git with fixed argv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gyrinx.devserver.processes import (  # noqa: E402
    OWNER_ENV,
    Owner,
    ProcessInspectionError,
    find_owner,
    group_processes,
    process_start,
)


def state_path(root):
    return root / "logs/dev-server.json"


def read_state(root):
    try:
        state = json.loads(state_path(root).read_text())
        if isinstance(state, dict) and state.get("worktree") == str(root):
            return state
    except OSError, ValueError:
        return None
    return None


def write_state(root, state):
    path = state_path(root)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(path)


def supervisor_alive(state):
    return bool(
        state
        and state.get("state") != "stopped"
        and state.get("started")
        and process_start(state.get("pid")) == state["started"]
    )


def group_state(state):
    if not state or not (members := group_processes(state.get("group_pid"))):
        return "gone"
    identities = [
        {"pid": state.get("group_pid"), "started": state.get("group_started")},
        *state.get("group_members", []),
    ]
    return (
        "verified" if any(member in identities for member in members) else "unverified"
    )


def group_alive(state):
    return group_state(state) == "verified"


def group_gone(pgid, timeout=2):
    deadline = time.monotonic() + timeout
    while group_processes(pgid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


def status(root):
    state = read_state(root)
    running = supervisor_alive(state)
    print(f"Worktree: {root}")
    group = "gone" if running else group_state(state)
    label = (
        state["state"]
        if running
        else {
            "gone": "stopped",
            "verified": "orphaned",
            "unverified": "orphaned (unverified)",
        }[group]
    )
    print(f"State: {label}")
    if state:
        owner = Owner.decode(json.dumps(state.get("owner")))
        if owner:
            print(f"Owner: {owner.name} (pid {owner.pid}, started {owner.started} UTC)")
        else:
            print("Owner: unverified; idle expiry applies")
        if state.get("session_id"):
            print(f"Session: {state['session_id']}")
        if running and state.get("port"):
            print(f"URL: http://localhost:{state['port']}")
        if not running and state.get("reason"):
            print(f"Reason: {state['reason']}")
    print(f"Logs: {root / 'logs/dev-supervisor.log'}")


def open_lock(root):
    (root / "logs").mkdir(exist_ok=True)
    lock = (root / "logs/dev-server.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    return lock


def stop(root):
    state = read_state(root)
    if not supervisor_alive(state):
        group = group_state(state)
        if group == "unverified":
            print(
                f"Cannot verify surviving dev-server group in {root}; recovery record retained."
            )
            return 1
        if group == "verified":
            stop_group(state["group_pid"])
            if not group_gone(state["group_pid"]):
                print(
                    f"Dev-server processes remain in {root}; recovery record retained."
                )
                return 1
            print(f"Stopped orphaned dev-server process group in {root}.")
            return 0
        print(f"No managed dev server is running in {root}.")
        return 0
    # Check both PID and birth time before signalling; a stale record must
    # never stop an unrelated process which has reused the same PID.
    try:
        os.kill(state["pid"], signal.SIGTERM)
    except ProcessLookupError:
        return 0
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not supervisor_alive(state):
            if group_processes(state.get("group_pid")):
                print(
                    f"Dev-server processes remain in {root}; recovery record retained."
                )
                return 1
            print(f"Stopped dev server in {root}.")
            return 0
        time.sleep(0.1)
    print(f"Dev server did not stop; inspect {root / 'logs/dev-supervisor.log'}.")
    return 1


def stop_group(pid, child=None):
    """Stop descendants even when the shell or npm parent has already exited."""
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if child:
            child.poll()  # Reap the group leader if it exited.
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        # The group exited between the last probe and KILL.
        pass
    if child:
        child.wait()


def supervise(root, args, lock):
    owner = find_owner()
    state = {
        "worktree": str(root),
        "pid": os.getpid(),
        "started": process_start(os.getpid()),
        "owner": json.loads(owner.encode()) if owner else None,
        "session_id": (owner.session_id if owner else "")
        or os.environ.get("CODEX_THREAD_ID", ""),
        "state": "starting",
        "port": None,
    }
    if not state["started"]:
        raise RuntimeError("Cannot verify the dev-server supervisor process identity.")
    ready = root / "logs/dev-ready"
    ready.unlink(missing_ok=True)
    write_state(root, state)
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous_handlers = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    }
    child = None
    reason = "startup failed"
    try:
        child = subprocess.Popen(
            ["/bin/bash", str(root / "scripts/dev.sh"), "--managed-child", *args],
            cwd=root,
            env={**os.environ, OWNER_ENV: owner.encode() if owner else ""},
            start_new_session=True,
        )
        state.update(
            group_pid=child.pid,
            group_started=process_start(child.pid),
            group_members=group_processes(child.pid),
        )
        write_state(root, state)
        next_owner_check = 0
        while child.poll() is None:
            if stopping:
                reason = "stop requested"
                break
            if not (root / ".git").exists():
                reason = "worktree removed"
                break
            if time.monotonic() >= next_owner_check:
                try:
                    if owner and not owner.alive():
                        reason = (
                            f"owning {owner.name} process exited or its PID was reused"
                        )
                        break
                    members = group_processes(child.pid)
                    if members != state["group_members"]:
                        state["group_members"] = members
                        write_state(root, state)
                except ProcessInspectionError as exc:
                    print(str(exc), flush=True)
                next_owner_check = time.monotonic() + 5
            if state["state"] == "starting" and ready.exists():
                try:
                    port = int(ready.read_text().strip())
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        pass
                    state.update(state="running", port=port)
                    write_state(root, state)
                except OSError, ValueError:
                    # Retry while Django is still starting.
                    pass
            time.sleep(0.2)
        else:
            reason = (
                f"server command exited ({child.returncode}); see logs/runserver.log"
            )
        return_code = child.returncode or 0
    finally:
        cleaned = True
        if child:
            stop_group(child.pid, child)
            try:
                cleaned = group_gone(child.pid)
            except ProcessInspectionError as exc:
                print(str(exc), flush=True)
                cleaned = False
        if not cleaned:
            reason = "cleanup could not be verified; recovery record retained"
        print(f"Stopping dev server: {reason}.", flush=True)
        state.update(state="stopped" if cleaned else "orphaned", reason=reason)
        if state_path(root).parent.exists():
            write_state(root, state)
        lock.close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    return return_code if cleaned else 1


def start(root, args, background):
    lock = open_lock(root)
    if lock is None:
        print("This worktree already has a dev-server supervisor.")
        status(root)
        return 0
    if group_state(read_state(root)) != "gone":
        lock.close()
        print(
            "An orphaned dev-server group is still running. Run ./scripts/dev.sh --stop first."
        )
        return 1
    owner = find_owner()
    # An explicit empty owner prevents detached ancestry from adopting a
    # different process. Unverified ownership gets the bounded idle policy.
    os.environ[OWNER_ENV] = owner.encode() if owner else ""
    if not background:
        return supervise(root, args, lock)
    with (root / "logs/dev-supervisor.log").open("a") as log:
        child = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--supervise",
                str(lock.fileno()),
                str(root),
                *args,
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(lock.fileno(),),
        )
    lock.close()  # The detached supervisor retains the lock on this description.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = read_state(root)
        if state and state.get("pid") == child.pid:
            status(root)
            return 0
        if child.poll() is not None:
            print(
                f"Dev-server startup failed; inspect {root / 'logs/dev-supervisor.log'}."
            )
            return 1
        time.sleep(0.1)
    print(f"Dev server is starting; inspect {root / 'logs/dev-supervisor.log'}.")
    return 0


def prune(root):
    result = subprocess.run(  # nosec B607 — fixed git command
        ["git", "worktree", "list", "--porcelain"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    failures = 0
    for line in result.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        worktree = Path(line.removeprefix("worktree ")).resolve()
        state = read_state(worktree)
        if not state:
            continue
        owner = Owner.decode(json.dumps(state.get("owner")))
        if supervisor_alive(state):
            if owner and not owner.alive():
                failures += stop(worktree)
        else:
            if group_state(state) != "gone" and stop(worktree):
                failures += 1
                continue
            lock = open_lock(worktree)
            if lock:
                try:
                    if read_state(worktree) == state:
                        state_path(worktree).unlink(missing_ok=True)
                        print(f"Removed stopped dev-server record: {worktree}")
                finally:
                    lock.close()
    return int(bool(failures))


def main(args):
    root = ROOT.resolve()
    if args and args[0] == "--supervise":
        return supervise(
            Path(args[2]).resolve(), args[3:], os.fdopen(int(args[1]), "a")
        )
    actions = {"--background", "--status", "--stop", "--prune"}.intersection(args)
    if len(actions) > 1:
        raise ValueError("Choose one of --background, --status, --stop or --prune.")
    action = next(iter(actions), None)
    if action in {"--status", "--stop", "--prune"}:
        if len(args) != 1:
            raise ValueError(f"{action} does not accept startup flags.")
        if action == "--status":
            status(root)
            return 0
        return stop(root) if action == "--stop" else prune(root)
    allowed = {"--background", "--no-watch", "--reset-db", "--reset-venv"}
    if unknown := set(args) - allowed:
        raise ValueError(f"Unknown startup flags: {', '.join(sorted(unknown))}")
    return start(
        root, [arg for arg in args if arg != "--background"], action == "--background"
    )


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, ProcessInspectionError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
