"""
Shared task-execution core.

Both the production Pub/Sub push handler (``gyrinx.tasks.views``) and the local
``DatabaseBackend`` (``gyrinx.tasks.local_backend``) run a task's underlying
function through :func:`run_task`. That way dev/test and prod fire *identical*
``task_started`` / ``task_finished`` signals and drive the same ``TaskExecution``
bookkeeping — the two delivery paths can't quietly diverge.

``run_task`` never re-raises a task's own exception: it captures it into a FAILED
``TaskResult`` and returns ``ok=False``. Callers decide what a failure means for
their transport (Pub/Sub returns 500 to nack; the local worker reschedules with
backoff; ImmediateBackend-style eager execution just records it).
"""

import json
import logging
import traceback

from django.tasks import TaskResult
from django.tasks.base import TaskError, TaskResultStatus
from django.tasks.signals import task_finished, task_started
from django.utils import timezone

from gyrinx.tracker import track

logger = logging.getLogger(__name__)


class TaskExecutionSender:
    """Sentinel ``sender`` for task lifecycle signals when a backend doesn't pass
    its own. The lifecycle receivers key off the ``TaskResult``, not the sender,
    so any stable class works — this just avoids importing a concrete backend
    (and its heavy deps) into the executor."""


class _MockTask:
    """Minimal stand-in Task so Django's built-in signal logging can read
    ``task_result.task.module_path``. When we execute from a queue row (or a
    Pub/Sub envelope) we only have the task *name*, not the original Task
    object."""

    def __init__(self, name: str):
        self.module_path = name


def build_task_result(
    task_id: str,
    task_name: str,
    args: list,
    kwargs: dict,
    status: TaskResultStatus,
    enqueued_at=None,
    return_value=None,
    error: Exception | None = None,
) -> TaskResult:
    """Construct a ``TaskResult`` for firing task lifecycle signals.

    Mirrors the object Django's own backends build. ``_return_value`` is only
    attached for a successful, JSON-serialisable result (matching what the
    signal handler persists onto ``TaskExecution``).
    """
    now = timezone.now()

    errors = []
    if error is not None:
        exception_type = type(error)
        errors.append(
            TaskError(
                exception_class_path=f"{exception_type.__module__}.{exception_type.__qualname__}",
                traceback="".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                ),
            )
        )

    result = TaskResult(
        task=_MockTask(task_name),
        id=task_id,
        status=status,
        enqueued_at=enqueued_at,
        started_at=now if status == TaskResultStatus.RUNNING else None,
        finished_at=now
        if status in (TaskResultStatus.SUCCESSFUL, TaskResultStatus.FAILED)
        else None,
        last_attempted_at=now,
        args=args,
        kwargs=kwargs,
        backend="default",
        errors=errors,
        worker_ids=[],
    )

    if return_value is not None and status == TaskResultStatus.SUCCESSFUL:
        try:
            json.dumps(return_value)
            object.__setattr__(result, "_return_value", return_value)
        except (TypeError, ValueError):
            logger.debug(
                "Task return value is not JSON-serializable, not storing",
                extra={"task_id": task_id},
            )

    return result


def run_task(
    func,
    *,
    task_name: str,
    task_id: str,
    args: list,
    kwargs: dict,
    enqueued_at=None,
    sender=None,
    track_extra: dict | None = None,
    emit_signals: bool = True,
):
    """Run ``func(*args, **kwargs)`` with full task lifecycle signalling.

    Fires ``task_started`` before and ``task_finished`` after. Returns a
    ``(ok, return_value, error)`` tuple. A task raising is *not* propagated —
    it becomes ``ok=False`` with the exception in ``error`` — so every transport
    can apply its own retry/ack policy uniformly.

    ``emit_signals=False`` runs the function without firing the lifecycle
    signals or touching the ``TaskExecution`` record. The local backend uses
    this for *duplicate* deliveries (at-least-once redelivery of an already
    completed task): the business logic runs again — which is exactly what
    idempotency needs to survive — but the canonical outcome record is left
    alone rather than being illegally resurrected out of its terminal state.
    """
    sender = sender or TaskExecutionSender
    extra = dict(track_extra or {})

    if emit_signals:
        started = build_task_result(
            task_id, task_name, args, kwargs, TaskResultStatus.RUNNING, enqueued_at
        )
        task_started.send(sender=sender, task_result=started)
    track("task_started", task_id=task_id, task_name=task_name, **extra)

    try:
        return_value = func(*args, **kwargs)
    except Exception as e:
        if emit_signals:
            failed = build_task_result(
                task_id,
                task_name,
                args,
                kwargs,
                TaskResultStatus.FAILED,
                enqueued_at,
                error=e,
            )
            task_finished.send(sender=sender, task_result=failed)
        track(
            "task_failed",
            task_id=task_id,
            task_name=task_name,
            error=str(e),
            **extra,
        )
        logger.error(
            f"Task {task_name} failed: {e}",
            extra={"task_id": task_id, "task_name": task_name},
            exc_info=True,
        )
        return False, None, e

    if emit_signals:
        finished = build_task_result(
            task_id,
            task_name,
            args,
            kwargs,
            TaskResultStatus.SUCCESSFUL,
            enqueued_at,
            return_value=return_value,
        )
        task_finished.send(sender=sender, task_result=finished)
    track("task_completed", task_id=task_id, task_name=task_name, **extra)
    return True, return_value, None
