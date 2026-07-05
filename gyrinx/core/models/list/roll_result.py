"""
Roll-table results gained by fighters (e.g. Spyrer Power Boosts).

A ListFighterRollResult records that a fighter has gained a specific
ContentRollTableRow via a ContentRollFlow ("spend counter points, roll on a
table"). It is a mod source (the row's modifiers apply to the fighter) and a
cost source (the copied rating_increase counts towards the fighter's rating),
mirroring how advancements work.
"""

import logging

from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase
from gyrinx.core.models.list.fighter import ListFighter

logger = logging.getLogger(__name__)


class ListFighterRollResult(AppBase):
    """A roll-table result a fighter has gained (e.g. a Power Boost)."""

    help_text = (
        "Records a roll-table result gained by a fighter, including the "
        "counter points spent and the rating increase applied."
    )

    fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="roll_results",
        help_text="The fighter who gained this result.",
    )
    row = models.ForeignKey(
        "content.ContentRollTableRow",
        on_delete=models.CASCADE,
        related_name="fighter_results",
        help_text="The roll table row that was gained.",
    )
    flow = models.ForeignKey(
        "content.ContentRollFlow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fighter_results",
        help_text="The flow this result came from (provenance).",
    )
    counter = models.ForeignKey(
        "content.ContentCounter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roll_results",
        help_text="The counter that was spent, kept for refunds on removal.",
    )
    counter_cost = models.IntegerField(
        default=0,
        help_text="Counter points spent to gain this result (copied from the flow).",
    )
    rating_increase = models.IntegerField(
        default=0,
        help_text="Rating increase applied when gained (copied from the row).",
    )
    date_received = models.DateTimeField(
        auto_now_add=True,
        help_text="When this result was gained.",
    )
    notes = models.TextField(blank=True)
    campaign_action = models.OneToOneField(
        "CampaignAction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roll_result",
        help_text="The campaign action recording the dice roll for this result.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-date_received"]
        verbose_name = "Fighter Roll Result"
        verbose_name_plural = "Fighter Roll Results"

    def __str__(self):
        return f"{self.fighter.name} - {self.row.name}"
