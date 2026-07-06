"""
Free-form counter spends recorded by fighters.

A ListFighterCounterSpend records that a fighter has spent points from a
counter without going through a roll flow — the user picks the amount and
supplies a purpose. Unlike a ListFighterRollResult it has no dice, no
roll-table row, and no rating impact; it exists purely as a durable,
refundable record of expenditure.

In campaign mode the spend is also mirrored to a CampaignAction (the purpose
is included in the description); outside a campaign the text is kept on the
record itself.
"""

from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase
from gyrinx.core.models.list.fighter import ListFighter


class ListFighterCounterSpend(AppBase):
    """A free-form spend of counter points by a fighter (no roll flow)."""

    help_text = (
        "Records counter points a fighter spent without a roll flow, along "
        "with the purpose, so the expenditure is auditable and refundable."
    )

    fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="counter_spends",
        help_text="The fighter who spent the counter points.",
    )
    counter = models.ForeignKey(
        "content.ContentCounter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spends",
        help_text="The counter that was spent, kept for refunds on removal.",
    )
    amount = models.PositiveIntegerField(
        help_text="Counter points spent.",
    )
    reason = models.TextField(
        blank=True,
        help_text="The purpose of the spend.",
    )
    date_spent = models.DateTimeField(
        auto_now_add=True,
        help_text="When the points were spent.",
    )
    campaign_action = models.OneToOneField(
        "CampaignAction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="counter_spend",
        help_text="The campaign action recording this spend, if in a campaign.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-date_spent"]
        verbose_name = "Fighter Counter Spend"
        verbose_name_plural = "Fighter Counter Spends"

    def __str__(self):
        counter_name = self.counter.name if self.counter else "counter"
        return f"{self.fighter.name} spent {self.amount} {counter_name}"
