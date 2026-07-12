"""Equipment sets ("Tools of the Trade" cards) for fighters.

A fighter with the "Tools of the Trade" rule can maintain several named cards,
each fielding a chosen subset of the equipment and weapons the fighter owns.

Key invariant: an equipment set is a *display-only view* over the fighter's
existing equipment. Every assignment stays owned by the fighter regardless of
which set is active — a set merely selects which of those assignments are
*shown*. Selecting a set never mutates the fighter's canonical cost, the gang
rating that feeds campaign credits / audit / cost-pins, or any cached
``rating_current``. The "selected rating" is computed as a fresh read and is
never persisted. See issue #1853.
"""

from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase


class ListFighterEquipmentSet(AppBase):
    """A named subset of a fighter's equipment (a Tools of the Trade card).

    The implicit "Default" card — every item the fighter owns — is represented
    by ``ListFighter.active_equipment_set is None``; there is no row for it.
    """

    help_text = (
        "A named subset of a fighter's equipment, shown as a separate card "
        "(Tools of the Trade)."
    )

    list_fighter = models.ForeignKey(
        "ListFighter",
        on_delete=models.CASCADE,
        related_name="equipment_sets",
        help_text="The fighter this equipment set belongs to.",
    )
    name = models.CharField(
        max_length=255,
        help_text="The name of this equipment set / card.",
    )
    assignments = models.ManyToManyField(
        "ListFighterEquipmentAssignment",
        related_name="equipment_sets",
        blank=True,
        help_text=(
            "The fighter's direct equipment assignments included in this set. "
            "Assignments not listed here are hidden while this set is active, "
            "but remain assigned to the fighter."
        ),
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["name", "created"]
        verbose_name = "Equipment Set"
        verbose_name_plural = "Equipment Sets"

    def __str__(self):
        return f"{self.name} ({self.list_fighter.name})"
