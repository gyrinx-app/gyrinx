"""Stop abandoned development servers and restart servers over their memory limit.

Check memory after the first request. Allow in-flight requests to drain
for up to DRAIN_SECONDS before restarting. Agent-owned servers stop when
their owner exits. Unowned servers have a bounded idle lifetime.

Use runserver's restart exit code only under its autoreloader; otherwise
stop. scripts/dev_server.py cleans up the whole process group on exit.
"""

import ctypes
import functools
import logging
import os
import sys
import threading
import time

from django.core.signals import request_finished, request_started

from gyrinx.devserver.processes import ProcessInspectionError, find_owner

logger = logging.getLogger(__name__)

#: Exit code that asks runserver's autoreloader to restart the serving process.
RESTART = 3
STOP = 0
#: How long a server over its memory limit waits for requests in flight.
DRAIN_SECONDS = 60


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
        alive=lambda owner: owner.alive(),
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

        if self.owner and not self.alive(self.owner):
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
            not self.owner
            and self.idle_minutes > 0
            and not in_flight
            and idle_for >= self.idle_minutes * 60
        ):
            return STOP, (
                f"it has had no requests for {minutes(self.idle_minutes)}, and "
                "it has no verified agent owner"
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
        elif self.idle_minutes > 0:
            rules.append(
                f"stops after {minutes(self.idle_minutes)} without a request "
                "(no verified agent owner)"
            )
        return rules

    def watch(self, interval=5.0):
        # Find the owner in the background thread so process lookups do not delay autoreload.
        try:
            self.owner = find_owner()
        except ProcessInspectionError as exc:
            logger.warning("Dev server guard: %s", exc)
        if rules := self.rules():
            logger.info("Dev server guard: %s.", "; ".join(rules))
        while True:
            time.sleep(interval)
            try:
                decision = self.check()
            except ProcessInspectionError as exc:
                logger.warning("Dev server guard: %s", exc)
                continue
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
