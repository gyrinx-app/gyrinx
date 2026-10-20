"""A Gang Tactic a gang has rolled and holds.

A gang earns the right to a tactic from its ranks — 2 for a Leader, 1 for
a Champion — and from the Develop Tactics action. That right is never a
row: it is read off the roster each time (``n26.core.tactics``), so a
promotion or a loss changes it with nothing to keep in step. What is a
row is each tactic once it has been rolled, together with the roll that
found it and the model whose rank paid for it.

The tactic is a library pickable on a Gang Tactics roll table (a
picklist), both referred to here by label: this module never imports the
library (``n26/core/models/AGENTS.md``).

A discarded tactic is archived rather than deleted, so the record of
what was rolled stays. A tactic rolled by the Develop Tactics action names
that action's record. Only one tactic of each kind may be held at a
time, which is the rule's "no duplicates" kept by the database.
"""

from django.db import models
from django.db.models import Q

from n26.core.models.abstract import Archived, Base


class GangTactic(Base, Archived):
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="tactics"
    )
    picklist = models.ForeignKey(
        "library.Picklist",
        on_delete=models.PROTECT,
        related_name="gang_tactics",
        help_text="The Gang Tactics table this was rolled on.",
    )
    pickable = models.ForeignKey(
        "library.Pickable",
        on_delete=models.PROTECT,
        related_name="gang_tactics",
        help_text="The tactic the roll landed on.",
    )
    roll = models.PositiveSmallIntegerField(
        help_text="The roll that landed on this tactic."
    )
    source = models.ForeignKey(
        "n26.Miniature",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gang_tactics",
        help_text="The model whose rank this tactic was rolled for.",
    )
    action_record = models.ForeignKey(
        "n26.ActionRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gang_tactics",
        help_text="The Develop Tactics action this tactic was rolled for, if any.",
    )

    class Meta:
        verbose_name = "gang tactic"
        verbose_name_plural = "gang tactics"
        ordering = ["created"]
        constraints = [
            models.UniqueConstraint(
                fields=["gang", "pickable"],
                condition=Q(archived=False),
                name="gang_tactic_held_once",
            )
        ]

    def __str__(self):
        return str(self.pickable)
