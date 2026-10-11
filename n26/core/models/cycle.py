"""A campaign's numbered cycles, whose identities survive name changes."""

from django.db import models
from django.utils import timezone

from n26.core.models.abstract import Base


class CampaignCycle(Base):
    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.PROTECT, related_name="cycles"
    )
    number = models.PositiveIntegerField()
    name = models.CharField(max_length=200, blank=True, default="")
    started = models.DateTimeField(default=timezone.now)
    ended = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "number"], name="campaign_cycle_number_unique"
            ),
            models.UniqueConstraint(
                fields=["campaign"],
                condition=models.Q(ended__isnull=True),
                name="campaign_cycle_one_current",
            ),
            models.CheckConstraint(
                condition=models.Q(number__gte=1), name="campaign_cycle_number_positive"
            ),
        ]

    @property
    def label(self):
        return f"Cycle {self.number}" + (f" · {self.name}" if self.name else "")
