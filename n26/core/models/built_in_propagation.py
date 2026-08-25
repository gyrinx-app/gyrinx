"""The propagation a set change files against everything already holding it.

An author adds a member to a set of defaults; every carrier already
drawing from that set should gain a copy. The write that files this
work and the pass that applies it are separated by a message queue
whose publish can be lost, so the work is a durable row filed in the
author's own transaction: however the message fares, the row says what
is not yet applied, and a scheduled sweep re-publishes anything left
standing (:mod:`n26.core.propagation`).

One row is one pass, single-shot and strictly forward: PENDING →
RUNNING → DONE or FAILED, no backward edges. Filing is append-only —
every edit inserts its own row, and rows are never shared or reused.
Reuse would race: a second edit attaching to a standing PENDING row can
find that row claimed, and its library read, before the edit commits —
the pass misses the change, the edit's own publish stands down at the
claim, and the change is silently never applied. A fresh row per edit
closes that for good, because a row's message publishes only after its
own edit commits, so the pass that claims it always reads a library
that includes the change that filed it. A redundant pass is a no-op by
the reconcile's idempotency. An ended row is never revived — a retry is
a fresh row — which leaves the table an append-only record of every
filing and how it ended.
"""

from django.db import models

from gyrinx.state_machine import StateMachine
from n26.core.models.abstract import Base


class BuiltInPropagationTask(Base):
    """One filed propagation pass over a set's holders."""

    # By label, as every core reference into the library is. The rows go
    # with their set: a filing is meaningless without the set it names,
    # and holding a never-used set undeletable over a row filed the
    # moment its first member landed would be worse than losing the
    # record. ``related_name="+"`` only drops the reverse accessor: the
    # library's reference scan walks hidden relations too, so it sees
    # this edge like any other. What keeps these rows out of an author's
    # view is that nothing downstream matches this field — no reach
    # sentence names it, and the delete page lists only edges that
    # protect, which a cascade never does.
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
