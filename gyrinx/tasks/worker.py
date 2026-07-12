"""
In-process delivery for the local durable queue.

This module holds:

- :func:`deliver` — run one *claimed* ``QueuedTask`` row and settle it (delete on
  success, reschedule with backoff on failure, give up after ``max_attempts``).
  Shared by the background worker pool and the manual pytest driver so both take
  the exact same delivery path.
- :class:`TaskWorkerPool` — a small pool of daemon threads that poll the queue and
  call :func:`deliver`. Lazily started by the ``DatabaseBackend`` in ``worker``
  mode (the dev server); never started under tests.

Nothing here runs in production — prod delivers via Pub/Sub push.
"""

import enum
import logging
import threading
from datetime import timedelta

from django.db import close_old_connections
from django.utils import timezone

from gyrinx.tasks.executor import run_task
from gyrinx.tasks.faults import FaultConfig
from gyrinx.tasks.registry import get_task

logger = logging.getLogger(__name__)

# Fallbacks when a task isn't in the registry (dev-only; prod requires registration).
DEFAULT_MIN_RETRY_DELAY = 10
DEFAULT_MAX_RETRY_DELAY = 600


class InjectedFailure(Exception):
    """Raised (conceptually) to represent a fault-injected delivery failure —
    a transient nack that never reflects a real bug in the task."""


class Outcome(str, enum.Enum):
    SUCCESS = "success"
    DROPPED = "dropped"  # fault-injected message loss
    RETRY_SCHEDULED = "retry_scheduled"
    GAVE_UP = "gave_up"  # exhausted max_attempts
    UNKNOWN_TASK = "unknown_task"


def _resolve(task_name):
    route = get_task(task_name)
    if route is None:
        return None, None
    return route._underlying_func, route


def compute_backoff(route, attempts: int) -> timedelta:
    """Exponential backoff bounded by the route's retry-delay window.

    ``attempts`` is the number of attempts made so far (>= 1), so the first retry
    waits ``min_retry_delay``, then doubles up to ``max_retry_delay`` — mirroring
    a Pub/Sub subscription's retry policy.
    """
    min_delay = route.min_retry_delay if route else DEFAULT_MIN_RETRY_DELAY
    max_delay = route.max_retry_delay if route else DEFAULT_MAX_RETRY_DELAY
    delay = min_delay * (2 ** max(0, attempts - 1))
    return timedelta(seconds=min(delay, max_delay))


def _reset_execution_for_attempt(task_id: str) -> None:
    """Return a ``TaskExecution`` to READY so a *retry* can transition it cleanly.

    ``TaskExecution`` models one execution with sticky terminal states; a retry is
    a fresh execution of the same logical task. Rather than widen the prod state
    machine, the local worker resets the row here (bypassing the state machine on
    purpose) before re-running, so ``task_started``'s READY→RUNNING stays valid.
    Local/observability-only; prod never calls this.

    SUCCESSFUL is excluded: if a worker crashed after ``run_task`` succeeded but
    before ``qt.delete()``, the lease lapses and the row is reclaimed — we must not
    resurrect the completed record back to READY (and re-run erasing the success).
    """
    from gyrinx.tasks.models import TaskExecution

    TaskExecution.objects.filter(task_id=task_id).exclude(
        status__in=["READY", "SUCCESSFUL"]
    ).update(
        status="READY",
        started_at=None,
        finished_at=None,
        error_message="",
        error_traceback="",
        modified=timezone.now(),
    )


def _mark_execution_failed(task_id: str, error) -> None:
    """Mark the observability row FAILED on final give-up, if not already terminal.

    After real task exceptions the row is already FAILED (run_task marked it). This
    matters for fault-injected give-ups, where the function never ran and the row is
    still READY.
    """
    from gyrinx.tasks.models import TaskExecution

    execution = TaskExecution.objects.filter(task_id=task_id).first()
    if execution and execution.status not in ("SUCCESSFUL", "FAILED"):
        execution.mark_failed(error_message=str(error)[:500])


def deliver(
    qt,
    *,
    force_fail: bool = False,
    drop: bool = False,
    fault: FaultConfig | None = None,
    sender=None,
) -> Outcome:
    """Deliver one already-claimed ``QueuedTask`` and settle its row.

    Assumes ``qt`` has been claimed (``attempts`` already incremented, lease held).
    Never raises for task failures — the caller's loop stays alive.

    - ``drop`` / a rolled ``fault.should_drop()`` → discard the row (message lost).
    - ``force_fail`` / a rolled ``fault.should_fail()`` → treat the delivery as a
      transient failure without running the function.
    - on success, an optional ``fault.should_duplicate()`` re-runs the function a
      second time (at-least-once) via ``emit_signals=False``.
    """
    func, route = _resolve(qt.task_name)
    if func is None:
        logger.error(
            "QueuedTask %s references unregistered task %r; discarding",
            qt.task_id,
            qt.task_name,
        )
        # enqueue() created a READY TaskExecution; mark it FAILED before dropping
        # the row so status/polling reflects that the work was discarded rather
        # than showing it stuck pending forever.
        _mark_execution_failed(qt.task_id, f"Unregistered task {qt.task_name!r}")
        qt.delete()
        return Outcome.UNKNOWN_TASK

    if fault is not None:
        fault.sleep()

    if drop or (fault is not None and fault.should_drop()):
        logger.warning(
            "Dropping delivery of %s (task_id=%s) — simulated message loss",
            qt.task_name,
            qt.task_id,
        )
        qt.delete()
        return Outcome.DROPPED

    inject_fail = force_fail or (fault is not None and fault.should_fail())

    if inject_fail:
        ok, error = False, InjectedFailure("fault-injected delivery failure")
    else:
        if qt.attempts > 1:
            # A retry re-runs a not-yet-succeeded task; make the row re-runnable.
            _reset_execution_for_attempt(qt.task_id)
        ok, _rv, error = run_task(
            func,
            task_name=qt.task_name,
            task_id=qt.task_id,
            args=qt.args,
            kwargs=qt.kwargs,
            enqueued_at=qt.enqueued_at,
            sender=sender,
            track_extra={"attempt": qt.attempts},
        )

    if ok:
        if fault is not None and fault.should_duplicate():
            logger.info(
                "Duplicate delivery of %s (task_id=%s) — exercising idempotency",
                qt.task_name,
                qt.task_id,
            )
            run_task(
                func,
                task_name=qt.task_name,
                task_id=qt.task_id,
                args=qt.args,
                kwargs=qt.kwargs,
                enqueued_at=qt.enqueued_at,
                sender=sender,
                track_extra={"attempt": qt.attempts, "duplicate": True},
                emit_signals=False,
            )
        qt.delete()
        return Outcome.SUCCESS

    # Failed delivery: retry with backoff, or give up.
    if qt.attempts_exhausted:
        logger.error(
            "QueuedTask %s (%s) gave up after %s attempt(s): %s",
            qt.task_id,
            qt.task_name,
            qt.attempts,
            error,
        )
        _mark_execution_failed(qt.task_id, error)
        qt.delete()
        return Outcome.GAVE_UP

    backoff = compute_backoff(route, qt.attempts)
    qt.available_at = timezone.now() + backoff
    qt.locked_until = None
    qt.locked_by = ""
    qt.last_error = str(error)[:2000]
    qt.save(
        update_fields=[
            "available_at",
            "locked_until",
            "locked_by",
            "last_error",
            "modified",
        ]
    )
    logger.info(
        "QueuedTask %s (%s) failed attempt %s; retrying in %ss",
        qt.task_id,
        qt.task_name,
        qt.attempts,
        int(backoff.total_seconds()),
    )
    return Outcome.RETRY_SCHEDULED


class TaskWorkerPool:
    """A pool of daemon threads that poll the durable queue and deliver tasks.

    Used only under the dev server. Threads are daemons: a runserver autoreload
    kills them, but the durable rows survive and are reclaimed once their lease
    lapses — so an interrupted task is redelivered rather than lost.
    """

    def __init__(
        self,
        *,
        num_workers: int = 2,
        lease_seconds: int = 300,
        poll_interval: float = 1.0,
        fault: FaultConfig | None = None,
    ):
        self.num_workers = max(1, num_workers)
        self.lease = timedelta(seconds=lease_seconds)
        self.poll_interval = poll_interval
        self.fault = fault or FaultConfig.disabled()
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._started = False
        self._lock = threading.Lock()

    def ensure_started(self) -> None:
        """Idempotently start the worker threads on first use."""
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            for i in range(self.num_workers):
                name = f"gyrinx-task-worker-{i}"
                t = threading.Thread(target=self._loop, name=name, daemon=True)
                t.start()
                self._threads.append(t)
            self._started = True
            logger.info(
                "Started local task worker pool (%s worker(s)%s)",
                self.num_workers,
                ", faults ON" if self.fault.enabled else "",
            )

    def notify(self) -> None:
        """Nudge idle workers that new work may be available (optimisation over
        pure polling)."""
        self._wake.set()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        for t in self._threads:
            t.join(timeout=timeout)
        still_alive = [t for t in self._threads if t.is_alive()]
        self._threads.clear()
        self._started = False
        # Only reset to a restartable state if the workers actually exited: then
        # ensure_started() can start fresh threads without _loop() seeing a stale
        # _stop and exiting immediately. If a join timed out (a long-running
        # delivery), leave _stop set so the lingering threads still wind down —
        # clearing it would let them keep running alongside a restarted pool and
        # double-deliver.
        if not still_alive:
            self._stop.clear()
            self._wake.clear()

    def _loop(self) -> None:
        from gyrinx.tasks.models import QueuedTask

        worker_id = threading.current_thread().name
        while not self._stop.is_set():
            # Each poll cycle gets a fresh connection state; a worker thread must
            # not hang onto (or share) a request's DB connection.
            close_old_connections()
            try:
                qt = QueuedTask.objects.claim_one(worker_id=worker_id, lease=self.lease)
            except Exception:
                logger.exception("Task worker failed to claim; backing off")
                qt = None

            if qt is None:
                self._wake.wait(self.poll_interval)
                self._wake.clear()
                continue

            try:
                deliver(qt, fault=self.fault)
            except Exception:
                # deliver() shouldn't raise for task failures, but never let an
                # unexpected error kill the worker thread.
                logger.exception(
                    "Unexpected error delivering task %s; leaving row for lease "
                    "expiry / redelivery",
                    getattr(qt, "task_id", "?"),
                )
            finally:
                close_old_connections()
