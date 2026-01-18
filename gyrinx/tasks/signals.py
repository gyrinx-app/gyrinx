"""
Signal handlers for Django task lifecycle events.

These handlers manage TaskExecution records based on task lifecycle
signals from Django's task framework. This makes TaskExecution tracking
work with any backend (ImmediateBackend, PubSubBackend, etc.).
"""

import logging

from django.dispatch import receiver
from django.tasks.base import TaskResultStatus
from django.tasks.signals import task_enqueued, task_finished, task_started
from django.utils import timezone

from gyrinx.tasks.models import TaskExecution
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)


@receiver(task_enqueued)
@traced("signal_task_enqueued")
def handle_task_enqueued(sender, task_result, **kwargs):
    """
    Create TaskExecution record when a task is enqueued.

    Args:
        sender: The backend class that enqueued the task
        task_result: TaskResult instance with task metadata
    """
    # Extract task name - handle both Task objects and raw functions
    if task_result.task is not None:
        if hasattr(task_result.task, "func"):
            task_name = task_result.task.func.__name__
        else:
            task_name = getattr(task_result.task, "__name__", str(task_result.task))
    else:
        task_name = "unknown"

    TaskExecution.objects.create(
        task_id=task_result.id,
        task_name=task_name,
        args=list(task_result.args) if task_result.args else [],
        kwargs=dict(task_result.kwargs) if task_result.kwargs else {},
        enqueued_at=task_result.enqueued_at or timezone.now(),
    )

    logger.debug(
        "Created TaskExecution for task %s (task_id=%s)",
        task_name,
        task_result.id,
    )


@receiver(task_started)
@traced("signal_task_started")
def handle_task_started(sender, task_result, **kwargs):
    """
    Update TaskExecution to RUNNING when task starts.

    Args:
        sender: The backend class executing the task
        task_result: TaskResult instance with task metadata
    """
    try:
        execution = TaskExecution.objects.get(task_id=task_result.id)

        # Skip if already running (idempotency for at-least-once delivery)
        if execution.status == "RUNNING":
            logger.debug(
                "Task %s already RUNNING, skipping (task_id=%s)",
                execution.task_name,
                task_result.id,
            )
            return

        execution.mark_running()
        logger.debug(
            "Marked task %s as RUNNING (task_id=%s)",
            execution.task_name,
            task_result.id,
        )

    except TaskExecution.DoesNotExist:
        logger.warning(
            "TaskExecution not found for task_id=%s in task_started signal",
            task_result.id,
        )


@receiver(task_finished)
@traced("signal_task_finished")
def handle_task_finished(sender, task_result, **kwargs):
    """
    Update TaskExecution to SUCCESSFUL or FAILED when task finishes.

    Args:
        sender: The backend class that executed the task
        task_result: TaskResult instance with task metadata and results
    """
    try:
        execution = TaskExecution.objects.get(task_id=task_result.id)

        # Skip if already completed (idempotency)
        if execution.status in ("SUCCESSFUL", "FAILED"):
            logger.debug(
                "Task %s already %s, skipping (task_id=%s)",
                execution.task_name,
                execution.status,
                task_result.id,
            )
            return

        if task_result.status == TaskResultStatus.SUCCESSFUL:
            # Extract return value from TaskResult
            return_value = getattr(task_result, "_return_value", None)
            execution.mark_successful(return_value=return_value)
            logger.debug(
                "Marked task %s as SUCCESSFUL (task_id=%s)",
                execution.task_name,
                task_result.id,
            )

        elif task_result.status == TaskResultStatus.FAILED:
            # Extract error information from TaskResult
            error_message = ""
            error_traceback = ""

            if task_result.errors:
                error = task_result.errors[0]
                # TaskError has exception_class_path and traceback attributes
                error_traceback = getattr(error, "traceback", "")

                # Extract actual error message from traceback's last line
                # Format: "ExceptionType: error message"
                if error_traceback:
                    last_line = error_traceback.strip().split("\n")[-1]
                    if ": " in last_line:
                        error_message = last_line.split(": ", 1)[1]
                    else:
                        error_message = last_line
                else:
                    # Fall back to exception class path
                    error_message = getattr(error, "exception_class_path", str(error))

            execution.mark_failed(
                error_message=error_message,
                error_traceback=error_traceback,
            )
            logger.debug(
                "Marked task %s as FAILED (task_id=%s): %s",
                execution.task_name,
                task_result.id,
                error_message,
            )

    except TaskExecution.DoesNotExist:
        logger.warning(
            "TaskExecution not found for task_id=%s in task_finished signal",
            task_result.id,
        )
