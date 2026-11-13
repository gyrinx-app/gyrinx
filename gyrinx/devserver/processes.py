"""Identify an agent before detaching its development server."""

import json
import os
import subprocess  # nosec B404 — fixed ps commands
from dataclasses import asdict, dataclass

AGENT_COMMANDS = {"claude": "Claude Code", "codex": "Codex"}
OWNER_ENV = "GYRINX_DEV_OWNER"


class ProcessInspectionError(RuntimeError):
    """Process identity could not be checked; do not assume the process died."""


def _ps(args):
    try:
        result = subprocess.run(  # nosec B607 — fixed executable and argv
            ["ps", *args],
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProcessInspectionError(
            "Cannot inspect local processes. Rerun with permission to inspect processes."
        ) from exc
    if result.returncode and result.stderr.strip():
        raise ProcessInspectionError(
            "Cannot inspect local processes. Rerun with permission to inspect processes."
        )
    return result.stdout.strip()


def ps(pid, columns):
    return _ps(["-o", columns, "-p", str(pid)])


def group_processes(pgid):
    """Read live group members and birth times without inspecting their arguments."""
    if type(pgid) is not int or pgid <= 1:
        return []
    result = []
    for line in _ps(["-axo", "pid=,pgid=,lstart=,stat="]).splitlines():
        fields = line.split(None, 2)
        if len(fields) != 3 or fields[1] != str(pgid):
            continue
        started, state = fields[2].rsplit(None, 1)
        if "Z" not in state:
            result.append({"pid": int(fields[0]), "started": started})
    return result


def process_start(pid):
    """Return a process's birth time, excluding zombies and missing processes."""
    if not isinstance(pid, int) or pid <= 1:
        return None
    line = ps(pid, "lstart=,stat=")
    started, _, state = line.rpartition(" ")
    if not started or not state or "Z" in state:
        return None
    return started.strip()


def process_alive(pid):
    return process_start(pid) is not None


@dataclass(frozen=True)
class Owner:
    pid: int
    name: str
    started: str
    session_id: str = ""

    def alive(self):
        return process_start(self.pid) == self.started

    def encode(self):
        return json.dumps(asdict(self))

    @classmethod
    def decode(cls, value):
        try:
            owner = cls(**json.loads(value))
            if (
                type(owner.pid) is int
                and owner.pid > 1
                and owner.name in AGENT_COMMANDS.values()
                and isinstance(owner.started, str)
                and owner.started
                and isinstance(owner.session_id, str)
            ):
                return owner
        except TypeError, ValueError:
            return None
        return None


def agent_name(command):
    for candidate in (command, command.split(" ", 1)[0]):
        name = AGENT_COMMANDS.get(os.path.basename(candidate))
        if name:
            return name
    return None


def find_owner(environ=os.environ, parent_pid=None, alive=process_alive):
    """Preserve explicit ownership across detachment and Django autoreloads.

    A dead explicit owner remains the owner, so it triggers cleanup rather
    than adopting a different ancestor or acquiring an unlimited lifetime.
    """
    if OWNER_ENV in environ:
        return Owner.decode(environ[OWNER_ENV])
    session_id = environ.get("CODEX_THREAD_ID", environ.get("CLAUDE_SESSION_ID", ""))

    def capture(pid, name):
        started = process_start(pid)
        if started and alive(pid):
            return Owner(pid, name, started, session_id)
        return None

    claude_pid = environ.get("CLAUDE_PID", "")
    if (
        claude_pid.isdigit()
        and agent_name(ps(int(claude_pid), "comm=")) == "Claude Code"
    ):
        if owner := capture(int(claude_pid), AGENT_COMMANDS["claude"]):
            return owner
    pid = os.getppid() if parent_pid is None else parent_pid
    for _ in range(16):
        if pid <= 1:
            break
        line = ps(pid, "ppid=,comm=")
        ppid, _, command = line.partition(" ")
        if not ppid.isdigit():
            break
        if name := agent_name(command.strip()):
            return capture(pid, name)
        pid = int(ppid)
    return None
