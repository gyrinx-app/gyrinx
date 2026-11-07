"""Execution results and durable delivery records for background tasks."""

import logging

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from gyrinx.models import Base
from gyrinx.state_machine import StateMachine

logger = logging.getLogger(__name__)

__all__ = ["TaskExecution", "QueuedTask"]


class TaskExecution(Base):
    """
    Persistent storage for task execution state and results.

    This model tracks the lifecycle of async tasks, from enqueueing through
    completion or failure. It integrates with Django's TaskResult framework
    to enable result retrieval via the task backend.

    Note: Does NOT inherit from AppBase since tasks are system-owned,
    not user-owned (no owner field needed).

    Attributes:
        task_id: External task ID from Django's task framework (TaskResult.id)
        task_name: The name of the task function
        args: Positional arguments passed to the task (JSON)
        kwargs: Keyword arguments passed to the task (JSON)
        return_value: The task's return value if successful (JSON)
        error_message: Error message if the task failed
        error_traceback: Full traceback if the task failed
        enqueued_at: When the task was enqueued
        started_at: When task execution began
        finished_at: When task execution completed

    State Machine (via states property):
        READY -> RUNNING: Task picked up by worker
        RUNNING -> SUCCESSFUL: Task completed successfully
        RUNNING -> FAILED: Task raised an exception
        READY -> FAILED: Task failed before starting (e.g., invalid args)
    """

    states = StateMachine(
        states=[
            ("READY", "Ready"),  # Enqueued, waiting to run
            ("RUNNING", "Running"),  # Currently executing
            ("SUCCESSFUL", "Successful"),  # Completed successfully
            ("FAILED", "Failed"),  # Failed with error
        ],
        initial="READY",
        transitions={
            "READY": ["RUNNING", "FAILED"],
            "RUNNING": ["SUCCESSFUL", "FAILED"],
        },
    )

    task_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="External task ID from Django's task framework (TaskResult.id)",
    )
    task_name = models.CharField(max_length=255, db_index=True)

    # Use an unguessable group key because status is readable by anyone who knows it.
    group_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Logical operation this task run belongs to (e.g. 'campaign-start:<uuid>').",
    )
    label = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Human-readable name for this unit of work within its group.",
    )

    args = models.JSONField(default=list)
    kwargs = models.JSONField(default=dict)

    return_value = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    error_traceback = models.TextField(blank=True)

    enqueued_at = models.DateTimeField(db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-enqueued_at"]
        indexes = [
            models.Index(fields=["task_name", "status"]),
            models.Index(fields=["status", "enqueued_at"]),
        ]
        verbose_name = "Task Execution"
        verbose_name_plural = "Task Executions"

    def __str__(self):
        return f"{self.task_name} ({self.status}) - {self.task_id}"

    def mark_running(self, metadata: dict | None = None) -> None:
        """Enter RUNNING and save the start time with optional transition metadata."""
        with transaction.atomic():
            self.started_at = timezone.now()
            self.states.transition_to("RUNNING", metadata=metadata, save=False)
            self.save(update_fields=["started_at", "status", "modified"])

    def mark_successful(self, return_value=None, metadata: dict | None = None) -> None:
        """Enter SUCCESSFUL and save a JSON-serialisable result with the finish time."""
        with transaction.atomic():
            self.finished_at = timezone.now()
            self.return_value = return_value
            self.states.transition_to("SUCCESSFUL", metadata=metadata, save=False)
            self.save(
                update_fields=["finished_at", "return_value", "status", "modified"]
            )

    def mark_failed(
        self,
        error_message: str,
        error_traceback: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Enter FAILED and save the error, optional traceback and finish time."""
        with transaction.atomic():
            self.finished_at = timezone.now()
            self.error_message = error_message
            self.error_traceback = error_traceback
            self.states.transition_to("FAILED", metadata=metadata, save=False)
            self.save(
                update_fields=[
                    "finished_at",
                    "error_message",
                    "error_traceback",
                    "status",
                    "modified",
                ]
            )

    @property
    def is_complete(self) -> bool:
        """Return whether this execution ended successfully or failed."""
        return self.status in ("SUCCESSFUL", "FAILED")

    @property
    def is_success(self) -> bool:
        """Return whether this execution ended successfully."""
        return self.status == "SUCCESSFUL"

    @property
    def is_failed(self) -> bool:
        """Return whether this execution failed."""
        return self.status == "FAILED"

    @property
    def duration(self):
        """Return elapsed execution time, or None until both timestamps are present."""
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None


class QueuedTaskQuerySet(models.QuerySet):
    """QuerySet helpers for the local durable queue."""

    def deliverable(self, now=None):
        """Select due deliveries with no lease or an expired lease.

        Expired leases allow another worker to reclaim tasks after a worker stops.
        """
        now = now or timezone.now()
        return self.filter(available_at__lte=now).filter(
            Q(locked_until__isnull=True) | Q(locked_until__lte=now)
        )


class QueuedTaskManager(models.Manager.from_queryset(QueuedTaskQuerySet)):
    def claim_one(self, *, worker_id, lease, now=None, ignore_schedule=False):
        """Lock and lease the next deliverable task, or return None.

        SKIP LOCKED lets concurrent workers claim different tasks without waiting.
        Increment attempts and save the worker and lease deadline atomically.
        With ignore_schedule=True, ignore available_at but retain lease checks
        so the manual test driver can retry without waiting for backoff.
        """
        now = now or timezone.now()
        with transaction.atomic():
            base = self if ignore_schedule else self.deliverable(now)
            if ignore_schedule:
                base = base.filter(
                    Q(locked_until__isnull=True) | Q(locked_until__lte=now)
                )
            row = (
                base.select_for_update(skip_locked=True)
                .order_by("available_at", "created")
                .first()
            )
            if row is None:
                return None
            row.attempts += 1
            row.locked_until = now + lease
            row.locked_by = worker_id
            row.save(
                update_fields=["attempts", "locked_until", "locked_by", "modified"]
            )
            return row


class QueuedTask(Base):
    """A durable, at-least-once message on the local in-process queue.

    Used only by the local ``DatabaseBackend`` (dev + tests); production uses
    Pub/Sub and never touches this table. The row is the unit of delivery: it is
    created on enqueue, leased by a worker while it runs, and deleted once the
    task succeeds (or is permanently given up after ``max_attempts``). The
    companion ``TaskExecution`` row records *what happened*; this row records
    *what still needs delivering*.
    """

    task_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Matches TaskExecution.task_id (the Django TaskResult.id).",
    )
    task_name = models.CharField(max_length=255, db_index=True)

    args = models.JSONField(default=list)
    kwargs = models.JSONField(default=dict)

    enqueued_at = models.DateTimeField()
    available_at = models.DateTimeField(
        db_index=True,
        help_text="Earliest delivery time. Set forward for deferred tasks and "
        "for retry backoff.",
    )

    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)

    locked_until = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Visibility lease: while set and in the future, the row is "
        "hidden from other workers.",
    )
    locked_by = models.CharField(max_length=64, blank=True, default="")
    last_error = models.TextField(blank=True, default="")

    objects = QueuedTaskManager()

    class Meta:
        ordering = ["available_at", "created"]
        indexes = [
            models.Index(fields=["available_at", "locked_until"]),
            models.Index(fields=["task_name"]),
        ]
        verbose_name = "Queued Task"
        verbose_name_plural = "Queued Tasks"

    def __str__(self):
        return f"{self.task_name} (attempt {self.attempts}/{self.max_attempts}) - {self.task_id}"

    @property
    def attempts_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts
