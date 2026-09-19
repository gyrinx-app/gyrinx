"""Records a change to a built-in set and tracks its async propagation.

One row per edit, created in the edit's own transaction. Strictly
forward: PENDING → RUNNING → DONE or FAILED; a retry is a fresh row,
so the table is a permanent record of every run and how it ended.
Rows are never shared or reused — why, and how the runs work, is
:mod:`n26.core.propagation`'s story.
"""

from django.db import models

from gyrinx.state_machine import StateMachine
from n26.core.models.abstract import Base


class BuiltInPropagationTask(Base):
    # By label, as every core reference into the library is. CASCADE: a
    # filing is meaningless without the set it names. ``related_name="+"``
    # only drops the reverse accessor — the library's reference scan still
    # walks this edge. Authors do not see these rows because nothing
    # downstream matches the field, and the delete page lists only edges
    # that protect, which a cascade never does.
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
