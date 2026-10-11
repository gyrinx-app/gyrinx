"""Immutable receipts and physical-source claims for per-cycle rewards."""

from django.db import models

from n26.core.models.abstract import Base


class CycleResolution(Base):
    cycle = models.ForeignKey(
        "n26.CampaignCycle", on_delete=models.PROTECT, related_name="resolutions"
    )
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.PROTECT, related_name="cycle_resolutions"
    )
    actor = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True)
    comment = models.CharField(max_length=255, blank=True)
    snapshot = models.JSONField(default=dict)
    batch = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cycle", "gang"], name="cycle_resolution_gang_unique"
            )
        ]


class CycleRewardClaim(Base):
    resolution = models.ForeignKey(
        CycleResolution, on_delete=models.PROTECT, related_name="claims"
    )
    cycle = models.ForeignKey(
        "n26.CampaignCycle", on_delete=models.PROTECT, related_name="claims"
    )
    source = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cycle", "source"], name="cycle_reward_source_unique"
            )
        ]
