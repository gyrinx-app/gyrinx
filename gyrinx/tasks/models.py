"""
Task execution models for storing task state and results.

This module provides persistent storage for task execution data,
allowing result retrieval and status tracking for async tasks.
"""

import logging

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils import timezone

from gyrinx.core.models.state_machine import StateMachineMixin
from gyrinx.models import Base

logger = logging.getLogger(__name__)

__all__ = ["TaskExecution"]


class TaskExecution(StateMachineMixin, Base):
    """
    Persistent storage for task execution state and results.

    This model tracks the lifecycle of async tasks, from enqueueing through
    completion or failure. It integrates with Django's TaskResult framework
    to enable result retrieval via the task backend.

    Note: Does NOT inherit from AppBase since tasks are system-owned,
    not user-owned (no owner field needed).

    Attributes:
        task_name: The name of the task function
        args: Positional arguments passed to the task (JSON)
        kwargs: Keyword arguments passed to the task (JSON)
        return_value: The task's return value if successful (JSON)
        error_message: Error message if the task failed
        error_traceback: Full traceback if the task failed
        enqueued_at: When the task was enqueued
        started_at: When task execution began
        finished_at: When task execution completed

    State Machine:
        READY -> RUNNING: Task picked up by worker
        RUNNING -> SUCCESSFUL: Task completed successfully
        RUNNING -> FAILED: Task raised an exception
        READY -> FAILED: Task failed before starting (e.g., invalid args)
    """

    # State machine configuration using Django's standard TaskResultStatus values
    STATES = [
        ("READY", "Ready"),  # Enqueued, waiting to run
        ("RUNNING", "Running"),  # Currently executing
        ("SUCCESSFUL", "Successful"),  # Completed successfully
        ("FAILED", "Failed"),  # Failed with error
    ]
    INITIAL_STATE = "READY"
    TRANSITIONS = {
        "READY": ["RUNNING", "FAILED"],
        "RUNNING": ["SUCCESSFUL", "FAILED"],
    }

    # Task identification
    task_name = models.CharField(max_length=255, db_index=True)

    # Task arguments (stored as JSON)
    args = models.JSONField(default=list)
    kwargs = models.JSONField(default=dict)

    # Result storage
    return_value = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    error_traceback = models.TextField(blank=True)

    # Timing
    enqueued_at = models.DateTimeField(db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # State transitions (GenericRelation for reverse lookups)
    state_transitions = GenericRelation(
        "core.StateTransition",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        ordering = ["-enqueued_at"]
        indexes = [
            models.Index(fields=["task_name", "status"]),
            models.Index(fields=["status", "enqueued_at"]),
        ]
        verbose_name = "Task Execution"
        verbose_name_plural = "Task Executions"

    def __str__(self):
        return f"{self.task_name} ({self.status}) - {self.id}"

    def mark_running(self, metadata: dict | None = None) -> None:
        """
        Mark the task as running and record start time.

        Args:
            metadata: Optional metadata to store with the transition
        """
        self.started_at = timezone.now()
        self.save(update_fields=["started_at", "modified"])
        self.transition_to("RUNNING", metadata=metadata, save=False)
        # Save again to ensure status is persisted (transition_to with save=False)
        self.save(update_fields=["status", "modified"])

    def mark_successful(self, return_value=None, metadata: dict | None = None) -> None:
        """
        Mark the task as successfully completed.

        Args:
            return_value: The return value from the task (must be JSON-serializable)
            metadata: Optional metadata to store with the transition
        """
        self.finished_at = timezone.now()
        self.return_value = return_value
        self.save(update_fields=["finished_at", "return_value", "modified"])
        self.transition_to("SUCCESSFUL", metadata=metadata, save=False)
        self.save(update_fields=["status", "modified"])

    def mark_failed(
        self,
        error_message: str,
        error_traceback: str = "",
        metadata: dict | None = None,
    ) -> None:
        """
        Mark the task as failed.

        Args:
            error_message: The error message
            error_traceback: The full traceback (optional)
            metadata: Optional metadata to store with the transition
        """
        self.finished_at = timezone.now()
        self.error_message = error_message
        self.error_traceback = error_traceback
        self.save(
            update_fields=[
                "finished_at",
                "error_message",
                "error_traceback",
                "modified",
            ]
        )
        self.transition_to("FAILED", metadata=metadata, save=False)
        self.save(update_fields=["status", "modified"])

    @property
    def is_complete(self) -> bool:
        """Check if the task has completed (successfully or with failure)."""
        return self.status in ("SUCCESSFUL", "FAILED")

    @property
    def is_success(self) -> bool:
        """Check if the task completed successfully."""
        return self.status == "SUCCESSFUL"

    @property
    def is_failed(self) -> bool:
        """Check if the task failed."""
        return self.status == "FAILED"

    @property
    def duration(self):
        """
        Calculate the task's execution duration.

        Returns:
            timedelta if task has both started_at and finished_at, else None
        """
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None
