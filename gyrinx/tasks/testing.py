"""
Pytest driver for the local task queue.

The ``task_queue`` fixture flips the backend into ``manual`` mode for one test:
enqueued tasks land in the durable ``QueuedTask`` table but nothing runs until the
test says so. The test then drives delivery deterministically and can script the
exact adverse conditions the production Pub/Sub path can throw at the task —
duplicate delivery, transient failure, message loss, ordering — to prove the
codebase's at-least-once/idempotency hardening actually holds.

Example::

    def test_redelivery_is_idempotent(task_queue, ...):
        with task_queue.capture():           # fire on_commit enqueues
            do_thing_that_enqueues()
        task_queue.deliver_all()             # run it once
        task_queue.redeliver_last()          # at-least-once duplicate
        assert ...                           # effect applied exactly once

    def test_recovers_from_transient_failure(task_queue, ...):
        with task_queue.capture():
            do_thing_that_enqueues()
        task_queue.fail_next()               # first attempt nacks
        task_queue.deliver_all()             # backoff → retry → success
        assert ...
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
    """Deterministic, in-thread driver over the ``QueuedTask`` table.

    All delivery runs in the test's own thread and transaction, so it sees the
    test's uncommitted data — unlike the real worker pool, which is why tests use
    this rather than starting threads.
    """

    def __init__(self, capture):
        self._capture = capture
        self._fail_countdown = 0
        self._drop_countdown = 0
        self.delivered: list[dict] = []
        self._last: dict | None = None

    # -- capturing on_commit enqueues -------------------------------------------------

    def capture(self, execute: bool = True):
        """Context manager that runs ``transaction.on_commit`` callbacks on exit.

        Most enqueues are deferred to ``on_commit``; under ``@pytest.mark.django_db``
        those never fire on their own. Wrap the triggering code in this so the
        enqueue actually reaches the queue.
        """
        return self._capture(execute=execute)

    # -- scripting faults -------------------------------------------------------------

    def fail_next(self, n: int = 1) -> "ManualTaskQueue":
        """Force the next ``n`` deliveries to fail (transient nack → retry/backoff)."""
        self._fail_countdown += n
        return self

    def drop_next(self, n: int = 1) -> "ManualTaskQueue":
        """Silently lose the next ``n`` deliveries (the task never runs)."""
        self._drop_countdown += n
        return self

    # -- driving delivery -------------------------------------------------------------

    def pending(self) -> int:
        """How many task rows are still on the queue (undelivered/retrying)."""
        from gyrinx.tasks.models import QueuedTask

        return QueuedTask.objects.count()

    def deliver_next(self):
        """Claim and deliver a single task. Returns its ``Outcome`` or ``None`` if
        the queue is empty."""
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
        """Deliver every task until the queue drains (following retries). Returns
        the number of delivery attempts made."""
        count = 0
        for _ in range(max_rounds):
            outcome = self.deliver_next()
            if outcome is None:
                return count
            count += 1
        raise RuntimeError(
            "deliver_all exceeded max_rounds — a task may be looping "
            "(self-re-enqueue without a base case?)"
        )

    def redeliver_last(self):
        """Re-run the most recently delivered task (at-least-once duplicate).

        Runs the underlying function again with the same arguments and task_id but
        without touching the observability record — exactly how the worker handles
        a duplicate delivery of an already-completed task.
        """
        if self._last is None:
            raise RuntimeError("no task has been delivered yet")
        func, _route = _resolve(self._last["task_name"])
        if func is None:
            raise RuntimeError(f"unknown task {self._last['task_name']!r}")
        return run_task(
            func,
            task_name=self._last["task_name"],
            task_id=self._last["task_id"],
            args=self._last["args"],
            kwargs=self._last["kwargs"],
            sender=local_backend.DatabaseBackend,
            track_extra={"duplicate": True},
            emit_signals=False,
        )

    # -- assertions -------------------------------------------------------------------

    def delivered_names(self) -> list[str]:
        return [d["task_name"] for d in self.delivered]

    def succeeded(self) -> list[dict]:
        return [d for d in self.delivered if d["outcome"] == Outcome.SUCCESS]


@pytest.fixture
def task_queue(db, django_capture_on_commit_callbacks):
    """Put the local task backend in ``manual`` mode and hand back a
    :class:`ManualTaskQueue` for driving delivery. Cleans the queue on the way in
    and out."""
    from gyrinx.tasks.models import QueuedTask

    local_backend.set_mode_override("manual")
    QueuedTask.objects.all().delete()
    try:
        yield ManualTaskQueue(capture=django_capture_on_commit_callbacks)
    finally:
        local_backend.set_mode_override(None)
        QueuedTask.objects.all().delete()
