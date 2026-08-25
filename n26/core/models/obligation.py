"""The debt a set change files against everything already holding it.

An author adds a member to a set of defaults; every carrier already
drawing from that set is owed a copy. The write that creates the debt
and the pass that pays it are separated by a message queue whose
publish can be lost, so the debt is a durable row filed in the author's
own transaction: however the message fares, the row says what is owed,
and a scheduled sweep re-publishes anything left standing
(:mod:`n26.core.propagation`).

One row is one pass, single-shot and strictly forward: PENDING →
RUNNING → DONE or FAILED, no backward edges. Coalescing happens only
among queued work — a partial unique constraint allows one PENDING row
per set, so edits arriving before the pass starts share it. An edit
while a pass is RUNNING files a fresh row: a row never records *which*
change, the pass reconciles from the library as it stands, so the worst
the overlap can produce is one redundant no-op run. An ended row is
never revived — a retry is a fresh PENDING row — which leaves the table
an append-only record of every debt and how it ended.
"""

from django.db import models

from gyrinx.state_machine import StateMachine
from n26.core.models.abstract import Base


class ReconcileObligation(Base):
    """One owed propagation pass over a set's holders."""

    # By label, as every core reference into the library is. The rows go
    # with their set: an obligation is meaningless without the set it
    # names, and holding a never-used set undeletable over a debt filed
    # the moment its first member landed would be worse than losing the
    # record. No reverse relation — this is bookkeeping about the set,
    # not a route by which anybody holds it, and the reference sweeps
    # that ask "what uses this set" must not find it.
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
        verbose_name = "reconcile obligation"
        verbose_name_plural = "reconcile obligations"
        ordering = ["created"]
        constraints = [
            models.UniqueConstraint(
                fields=["default_set"],
                condition=models.Q(status="PENDING"),
                name="one_pending_obligation_per_set",
            ),
        ]

    def __str__(self):
        return f"{self.default_set}: {self.status}"
