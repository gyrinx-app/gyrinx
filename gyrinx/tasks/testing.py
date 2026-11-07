"""Drive the local durable task queue deterministically in tests.

The task_queue fixture selects manual mode. Capture on_commit callbacks
when triggering enqueues, then call deliver_all, fail_next, drop_next or
redeliver_last to test retry and duplicate-delivery behaviour.
"""

import logging
from datetime import timedelta

import pytest

from gyrinx.tasks import local_backend
from gyrinx.tasks.executor import run_task
from gyrinx.tasks.worker import Outcome, _resolve, deliver

logger = logging.getLogger(__name__)

_MANUAL_LEASE = timedelta(seconds=300)


class ManualTaskQueue:
    """Deliver queued tasks in the test's own thread and transaction.

    This makes uncommitted test data visible to tasks, unlike worker-pool threads.
    """

    def __init__(self, capture):
        self._capture = capture
        self._fail_countdown = 0
        self._drop_countdown = 0
        self.delivered: list[dict] = []
        self._last: dict | None = None

    def capture(self, execute: bool = True):
        """Run captured on_commit callbacks on context exit when execute=True.

        Transactional tests do not normally commit, so deferred enqueues require
        this capture around the triggering code.
        """
        return self._capture(execute=execute)

    def fail_next(self, n: int = 1) -> ManualTaskQueue:
        """Fail the next n deliveries, allowing retry with backoff."""
        self._fail_countdown += n
        return self

    def drop_next(self, n: int = 1) -> ManualTaskQueue:
        """Discard the next n deliveries without running their tasks."""
        self._drop_countdown += n
        return self

    def pending(self) -> int:
        """Count undelivered and retrying queue records."""
        from gyrinx.tasks.models import QueuedTask

        return QueuedTask.objects.count()

    def deliver_next(self):
        """Claim and deliver one task, or return None when none can be claimed.

        Ignore scheduled delivery times while retaining visibility-lease checks.
        """
        from gyrinx.tasks.models import QueuedTask

        qt = QueuedTask.objects.claim_one(
            worker_id="manual", lease=_MANUAL_LEASE, ignore_schedule=True
        )
        if qt is None:
            return None

        force_fail = False
        drop = False
        if self._drop_countdown > 0:
            self._drop_countdown -= 1
            drop = True
        elif self._fail_countdown > 0:
            self._fail_countdown -= 1
            force_fail = True

        payload = {
            "task_name": qt.task_name,
            "task_id": qt.task_id,
            "args": list(qt.args),
            "kwargs": dict(qt.kwargs),
        }
        outcome = deliver(
            qt,
            force_fail=force_fail,
            drop=drop,
            sender=local_backend.DatabaseBackend,
        )
        self._last = payload
        self.delivered.append({**payload, "outcome": outcome})
        return outcome

    def deliver_all(self, max_rounds: int = 1000) -> int:
        """Deliver tasks until the queue drains or one is deferred.

        Retries run immediately, but a paused task remains queued for a later call.
        Returns the number of delivery attempts made.
        """
        count = 0
        for _ in range(max_rounds):
            outcome = self.deliver_next()
            if outcome is None:
                return count
            count += 1
            if outcome == Outcome.DEFERRED:
                return count
        raise RuntimeError(
            "deliver_all exceeded max_rounds — a task may be looping "
            "(self-re-enqueue without a base case?)"
        )

    def redeliver_last(self, task_name: str | None = None):
        """Run a previously delivered task again without changing its execution record.

        Reuse its arguments and task ID. With task_name, select the most recent
        delivery of that named task; otherwise select the latest delivery.
        Write-admission checks still apply.
        """
        if task_name is not None:
            payload = next(
                (d for d in reversed(self.delivered) if d["task_name"] == task_name),
                None,
            )
            if payload is None:
                raise RuntimeError(f"no delivered task named {task_name!r}")
        else:
            payload = self._last
        if payload is None:
            raise RuntimeError("no task has been delivered yet")
        func, route = _resolve(payload["task_name"])
        if func is None:
            raise RuntimeError(f"unknown task {payload['task_name']!r}")
        from gyrinx.site.write_pause import task_delivery_gate

        with task_delivery_gate(route, payload["kwargs"]) as admission:
            if not admission.allowed:
                return Outcome.DEFERRED
            return run_task(
                func,
                task_name=payload["task_name"],
                task_id=payload["task_id"],
                args=payload["args"],
                kwargs=payload["kwargs"],
                sender=local_backend.DatabaseBackend,
                track_extra={"duplicate": True},
                emit_signals=False,
            )

    def delivered_names(self) -> list[str]:
        return [d["task_name"] for d in self.delivered]

    def succeeded(self) -> list[dict]:
        return [d for d in self.delivered if d["outcome"] == Outcome.SUCCESS]


@pytest.fixture
def task_queue(db, django_capture_on_commit_callbacks):
    """Select manual mode and yield a queue driver, clearing queue records before and after."""
    from gyrinx.tasks.models import QueuedTask

    local_backend.set_mode_override("manual")
    QueuedTask.objects.all().delete()
    try:
        yield ManualTaskQueue(capture=django_capture_on_commit_callbacks)
    finally:
        local_backend.set_mode_override(None)
        QueuedTask.objects.all().delete()
