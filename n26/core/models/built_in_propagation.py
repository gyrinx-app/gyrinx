"""Record each built-in edit and the outcome of its asynchronous propagation.

Create the task in the edit transaction. Tasks progress from PENDING to
RUNNING, then DONE or FAILED. Retrying creates a new row rather than
reusing a completed or failed task. See n26.core.propagation.
"""

from django.db import models

from gyrinx.state_machine import StateMachine
from n26.core.models.abstract import Base


class BuiltInPropagationTask(Base):
    # Cascade tasks with their built-in set. Suppressing the reverse accessor
    # does not hide this relation from library reference scans. The author-facing
    # delete page lists PROTECT references rather than these task rows.
    default_set = models.ForeignKey(
        "library.DefaultAssignmentSet",
        on_delete=models.CASCADE,
        related_name="+",
    )

    states = StateMachine(
        states=[
            ("PENDING", "Pending"),
            ("RUNNING", "Running"),
            ("DONE", "Done"),
            ("FAILED", "Failed"),
        ],
        initial="PENDING",
        transitions={
            "PENDING": ["RUNNING"],
            "RUNNING": ["DONE", "FAILED"],
        },
    )

    class Meta:
        verbose_name = "built-in propagation task"
        verbose_name_plural = "built-in propagation tasks"
        ordering = ["created"]

    def __str__(self):
        return f"{self.default_set}: {self.status}"
