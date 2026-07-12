"""
Local durable task backend (dev + tests only).

A drop-in replacement for Django's ``ImmediateBackend`` that adds real
asynchrony and Pub/Sub-like semantics without any Pub/Sub dependency and without
a second process. Production continues to use ``PubSubBackend`` — this backend is
never selected there.

Modes (``OPTIONS["mode"]``):

- ``eager`` (default; test default): run inline inside ``enqueue()``, exactly like
  ``ImmediateBackend``. Keeps the whole existing test suite synchronous and green.
- ``worker`` (dev server): persist the task to the ``QueuedTask`` table and let an
  in-process pool of daemon threads deliver it asynchronously, with retries,
  backoff, visibility leases, and optional fault injection.
- ``manual`` (opt-in in tests): persist the task but deliver nothing automatically;
  the pytest driver in ``gyrinx.tasks.testing`` drives delivery explicitly and can
  script duplicates, failures, drops, and slowness.

The durable ``QueuedTask`` row means a task survives a runserver autoreload: an
interrupted delivery's lease lapses and the row is redelivered rather than lost.
"""

import logging
import threading
import uuid

from django.tasks import TaskResult
from django.tasks.backends.base import BaseTaskBackend
from django.tasks.base import TaskResultStatus
from django.tasks.signals import task_enqueued
from django.utils import timezone

from gyrinx.tasks.executor import run_task
from gyrinx.tasks.faults import FaultConfig

logger = logging.getLogger(__name__)

VALID_MODES = ("eager", "worker", "manual")

# Test-only, process-wide mode override. The pytest `task_queue` fixture flips the
# backend to `manual` for a single test without fighting Django's cached task
# backend handler (which has no settings_changed reset hook for TASKS).
_mode_override: str | None = None
_override_lock = threading.Lock()


def set_mode_override(mode: str | None) -> None:
    global _mode_override
    if mode is not None and mode not in VALID_MODES:
        raise ValueError(f"Invalid task mode {mode!r}; expected one of {VALID_MODES}")
    with _override_lock:
        _mode_override = mode


def get_mode_override() -> str | None:
    return _mode_override


# The worker pool is a per-process singleton so every enqueue in `worker` mode
# feeds the same set of threads.
_pool = None
_pool_lock = threading.Lock()


def get_worker_pool(*, num_workers, lease_seconds, poll_interval, fault):
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            from gyrinx.tasks.worker import TaskWorkerPool

            _pool = TaskWorkerPool(
                num_workers=num_workers,
                lease_seconds=lease_seconds,
                poll_interval=poll_interval,
                fault=fault,
            )
    return _pool


def reset_worker_pool() -> None:
    """Stop and clear the singleton pool (test/teardown helper)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.stop()
            _pool = None


class DatabaseBackend(BaseTaskBackend):
    supports_get_result = True
    supports_defer = True  # run_after → QueuedTask.available_at
    supports_async_task = False
    supports_priority = False

    def __init__(self, alias, params):
        super().__init__(alias, params)
        opts = params.get("OPTIONS", {})
        mode = opts.get("mode", "eager")
        if mode not in VALID_MODES:
            raise ValueError(
                f"Invalid task backend mode {mode!r}; expected one of {VALID_MODES}"
            )
        self.mode = mode
        self.num_workers = int(opts.get("num_workers", 2))
        self.lease_seconds = int(opts.get("lease_seconds", 300))
        self.poll_interval = float(opts.get("poll_interval", 1.0))
        self.default_max_attempts = int(opts.get("max_attempts", 5))
        # Fault knobs come from OPTIONS if given, else from env (dev-server chaos).
        if "faults" in opts:
            self.fault = FaultConfig.from_options(opts.get("faults"))
        else:
            self.fault = FaultConfig.from_env()

    @property
    def effective_mode(self) -> str:
        return get_mode_override() or self.mode

    def _new_task_result(self, task, task_id, args, kwargs, enqueued_at):
        return TaskResult(
            task=task,
            id=task_id,
            status=TaskResultStatus.READY,
            enqueued_at=enqueued_at,
            started_at=None,
            finished_at=None,
            last_attempted_at=None,
            args=list(args),
            kwargs=dict(kwargs),
            backend=self.alias,
            errors=[],
            worker_ids=[],
        )

    def enqueue(self, task, args, kwargs):
        self.validate_task(task)

        task_id = uuid.uuid4().hex
        enqueued_at = timezone.now()
        task_result = self._new_task_result(task, task_id, args, kwargs, enqueued_at)

        # Create the observability record (READY) via the shared signal handler —
        # same path every backend uses.
        task_enqueued.send(sender=type(self), task_result=task_result)

        mode = self.effective_mode
        task_name = task.func.__name__

        if mode == "eager":
            # Inline, synchronous — behaviourally identical to ImmediateBackend.
            # No QueuedTask row: eager doesn't retry or persist, so there's nothing
            # to deliver later. Keeps the existing suite fast and unchanged.
            run_task(
                task.func,
                task_name=task_name,
                task_id=task_id,
                args=list(args),
                kwargs=dict(kwargs),
                enqueued_at=enqueued_at,
                sender=type(self),
            )
            return task_result

        # worker / manual: persist a durable queue row.
        from gyrinx.tasks.models import QueuedTask

        available_at = getattr(task, "run_after", None) or enqueued_at
        QueuedTask.objects.create(
            task_id=task_id,
            task_name=task_name,
            args=list(args),
            kwargs=dict(kwargs),
            enqueued_at=enqueued_at,
            available_at=available_at,
            max_attempts=self.default_max_attempts,
        )

        if mode == "worker":
            pool = get_worker_pool(
                num_workers=self.num_workers,
                lease_seconds=self.lease_seconds,
                poll_interval=self.poll_interval,
                fault=self.fault,
            )
            pool.ensure_started()
            pool.notify()

        # manual: leave the row for the test driver to deliver.
        return task_result

    def get_result(self, result_id):
        from gyrinx.tasks.models import TaskExecution

        try:
            execution = TaskExecution.objects.get(task_id=result_id)
        except TaskExecution.DoesNotExist:
            return None

        status_map = {
            "READY": TaskResultStatus.READY,
            "RUNNING": TaskResultStatus.RUNNING,
            "SUCCESSFUL": TaskResultStatus.SUCCESSFUL,
            "FAILED": TaskResultStatus.FAILED,
        }
        errors = []
        if execution.is_failed and execution.error_message:
            errors = [execution.error_message]

        return TaskResult(
            task=None,
            id=execution.task_id,
            status=status_map.get(execution.status, TaskResultStatus.READY),
            enqueued_at=execution.enqueued_at,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            last_attempted_at=execution.started_at,
            args=execution.args,
            kwargs=execution.kwargs,
            backend=self.alias,
            errors=errors,
            worker_ids=[],
        )
