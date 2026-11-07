"""Stop abandoned development servers and restart servers over their memory limit.

Check memory after the first request. Allow in-flight requests to drain
for up to DRAIN_SECONDS before restarting. Agent-owned servers also stop
when their owner exits or their configured idle timeout expires.

Use runserver's restart exit code only under its autoreloader; otherwise
stop. scripts/dev.sh cleans up its watchers when the server exits.
"""

import ctypes
import functools
import logging
import os
import subprocess  # nosec B404 — runs ps with fixed arguments
import sys
import threading
import time
from dataclasses import dataclass

from django.core.signals import request_finished, request_started

logger = logging.getLogger(__name__)

#: Exit code that asks runserver's autoreloader to restart the serving process.
RESTART = 3
STOP = 0
#: How long a server over its memory limit waits for requests in flight.
DRAIN_SECONDS = 60
AGENT_COMMANDS = {"claude": "Claude Code", "codex": "Codex"}


@dataclass(frozen=True)
class Owner:
    pid: int
    name: str


class _RusageInfoV0(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64)
        for name in (
            "ri_user_time",
            "ri_system_time",
            "ri_pkg_idle_wkups",
            "ri_interrupt_wkups",
            "ri_pageins",
            "ri_wired_size",
            "ri_resident_size",
            "ri_phys_footprint",
            "ri_proc_start_abstime",
            "ri_proc_exit_abstime",
        )
    ]


@functools.cache
def _libproc():
    try:
        return ctypes.CDLL("/usr/lib/libproc.dylib")
    except OSError:
        return None


def memory_mb():
    """This process's memory in MB, or None where it cannot be read.

    On macOS that is the physical footprint, the figure Activity Monitor shows,
    which counts memory the system has compressed. Resident size leaves that
    out, and a large idle server is mostly compressed. Elsewhere it is the
    resident size.
    """
    if sys.platform == "darwin":
        libproc = _libproc()
        info = _RusageInfoV0()
        if libproc is None or libproc.proc_pid_rusage(
            os.getpid(), 0, ctypes.byref(info)
        ):
            return None
        return info.ri_phys_footprint / 2**20
    try:
        with open("/proc/self/status") as status:
            lines = status.readlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return None


def process_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def agent_name(command):
    """Identify an agent from its executable path or process title."""
    for candidate in (command, command.split(" ", 1)[0]):
        name = AGENT_COMMANDS.get(os.path.basename(candidate))
        if name:
            return name
    return None


def find_owner(environ=os.environ, parent_pid=None, alive=process_alive):
    """Find a live CLAUDE_PID or an agent process among the server's ancestors.

    The explicit environment PID supports detached launches whose ancestry
    no longer includes the originating agent.
    """
    claude_pid = environ.get("CLAUDE_PID", "")
    if claude_pid.isdigit() and alive(int(claude_pid)):
        return Owner(int(claude_pid), AGENT_COMMANDS["claude"])
    pid = os.getppid() if parent_pid is None else parent_pid
    for _ in range(16):
        if pid <= 1:
            return None
        try:
            line = subprocess.run(  # nosec B607 — fixed argv; ps resolved from PATH
                ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        except OSError, subprocess.SubprocessError:
            return None
        if not line:
            return None
        ppid, _, command = line.partition(" ")
        name = agent_name(command.strip())
        if name:
            return Owner(pid, name)
        pid = int(ppid)
    return None


def minutes(count):
    return f"{count} minute" if count == 1 else f"{count} minutes"


class Guard:
    def __init__(
        self,
        *,
        memory_limit_mb,
        idle_minutes,
        owner,
        clock=time.monotonic,
        memory=memory_mb,
        alive=process_alive,
    ):
        self.memory_limit_mb = memory_limit_mb
        self.idle_minutes = idle_minutes
        self.owner = owner
        self.clock = clock
        self.memory = memory
        self.alive = alive
        self.lock = threading.Lock()
        self.in_flight = 0
        self.requested = False
        self.last_request = clock()
        self.over_limit_since = None

    def request_started(self, **kwargs):
        with self.lock:
            self.in_flight += 1
            self.requested = True
            self.last_request = self.clock()

    def request_finished(self, **kwargs):
        with self.lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.last_request = self.clock()

    def check(self):
        """Return an exit code and reason when a stop or restart condition is met."""
        now = self.clock()
        with self.lock:
            in_flight = self.in_flight
            requested = self.requested
            idle_for = now - self.last_request

        if self.owner and not self.alive(self.owner.pid):
            return STOP, (
                f"the {self.owner.name} session that started it "
                f"(pid {self.owner.pid}) has ended"
            )

        # Restart only after a request; an unused process would restart at the same size.
        limited = self.memory_limit_mb > 0 and requested
        used = self.memory() if limited else None
        if used is not None and used > self.memory_limit_mb:
            if self.over_limit_since is None:
                self.over_limit_since = now
            if not in_flight or now - self.over_limit_since >= DRAIN_SECONDS:
                return RESTART, (
                    f"it is using {used:,.0f} MB, over its "
                    f"{self.memory_limit_mb:,} MB limit"
                )
        else:
            self.over_limit_since = None

        if (
            self.owner
            and self.idle_minutes > 0
            and not in_flight
            and idle_for >= self.idle_minutes * 60
        ):
            return STOP, (
                f"it has had no requests for {minutes(self.idle_minutes)}, and "
                f"an agent session started it"
            )
        return None

    def rules(self):
        rules = []
        if self.memory_limit_mb > 0:
            # See exit_plan(): without the autoreloader the server stops.
            under_autoreloader = os.environ.get("RUN_MAIN") == "true"
            action = "restarts" if under_autoreloader else "stops"
            rules.append(f"{action} past {self.memory_limit_mb:,} MB")
        if self.owner:
            rules.append(f"stops when {self.owner.name} (pid {self.owner.pid}) exits")
            if self.idle_minutes > 0:
                rules.append(
                    f"stops after {minutes(self.idle_minutes)} without a request"
                )
        return rules

    def watch(self, interval=5.0):
        # Find the owner in the background thread so process lookups do not delay autoreload.
        self.owner = find_owner()
        if rules := self.rules():
            logger.info("Dev server guard: %s.", "; ".join(rules))
        while True:
            time.sleep(interval)
            decision = self.check()
            if decision:
                exit_server(*decision)


def exit_plan(code, reason, under_autoreloader):
    """Choose the exit code and message, restarting only when an autoreloader is present."""
    if code == RESTART and under_autoreloader:
        return RESTART, f"Restarting the dev server: {reason}."
    if code == RESTART:
        return STOP, (
            f"Stopping the dev server: {reason}. Without the autoreloader "
            "nothing can restart it. Start it again to carry on."
        )
    return STOP, (
        f"Stopping the dev server: {reason}. Run ./scripts/dev.sh to start it again."
    )


def exit_server(code, reason):
    code, message = exit_plan(code, reason, os.environ.get("RUN_MAIN") == "true")
    logger.warning(message)
    logging.shutdown()
    # Exit without waiting for server threads. The autoreloader restarts on RESTART
    # and exits on STOP.
    os._exit(code)


def start(*, memory_limit_mb, idle_minutes):
    if os.name == "nt":
        # On Windows os.kill(pid, 0) ends the process instead of probing it.
        return None
    guard = Guard(
        memory_limit_mb=memory_limit_mb, idle_minutes=idle_minutes, owner=None
    )
    request_started.connect(guard.request_started, weak=False)
    request_finished.connect(guard.request_finished, weak=False)
    threading.Thread(target=guard.watch, name="dev-server-guard", daemon=True).start()
    return guard
