"""Campaign dice rolls retain the raw result separately from its modifier."""

from django.db import models

from n26.core.models.abstract import Base


class CampaignRoll(Base):
    class Dice(models.TextChoices):
        D3 = "d3", "D3"
        D6 = "d6", "D6"
        D66 = "d66", "D66"

    class Source(models.TextChoices):
        GENERATED = "generated", "Rolled here"
        MANUAL = "manual", "Physical dice"

    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="dice_rolls"
    )
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    request_key = models.UUIDField(editable=False)
    reason = models.CharField(max_length=200)
    dice = models.CharField(max_length=3, choices=Dice)
    rolled = models.PositiveSmallIntegerField()
    modifier = models.IntegerField(default=0)
    source = models.CharField(max_length=9, choices=Source)
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    battle = models.ForeignKey(
        "n26.Battle", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    outcome = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "request_key"], name="campaign_roll_request_unique"
            )
        ]
        ordering = ["created", "id"]

    @property
    def total(self):
        return self.rolled + self.modifier

    @property
    def calculation(self):
        raw = f"{self.get_dice_display()}: {self.rolled}"
        if not self.modifier:
            return raw
        sign = "+" if self.modifier > 0 else "−"
        return f"{raw} {sign} {abs(self.modifier)} = {self.total}"
