"""Campaign dice rolls retain the raw result separately from its modifier."""

from django.db import models

from n26.core.models.abstract import Base


class CampaignRoll(Base):
    class Dice(models.TextChoices):
        D3 = "d3", "D3"
        D6 = "d6", "D6"
        D66 = "d66", "D66"

    MAX_DICE = 20

    class ModifierApplication(models.TextChoices):
        TOTAL = "total", "Total"
        EACH = "each", "Each die"

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
    count = models.PositiveSmallIntegerField(default=1)
    results = models.JSONField(default=list, blank=True)
    modifier = models.IntegerField(default=0)
    modifier_application = models.CharField(
        max_length=5, choices=ModifierApplication, default=ModifierApplication.TOTAL
    )
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

    @classmethod
    def valid_total(cls, dice, count, rolled):
        """Check a physical total without claiming to know its individual dice."""
        if type(count) is not int or not 1 <= count <= cls.MAX_DICE:
            return False
        if type(rolled) is not int:
            return False
        match dice:
            case cls.Dice.D3:
                return count <= rolled <= 3 * count
            case cls.Dice.D6:
                return count <= rolled <= 6 * count
            case cls.Dice.D66:
                return any(
                    count <= rolled - 10 * tens <= 6 * count
                    for tens in range(count, 6 * count + 1)
                )
        return False

    @property
    def applied_modifier(self):
        return self.modifier * (
            self.count
            if self.modifier_application == self.ModifierApplication.EACH
            else 1
        )

    @property
    def total(self):
        return self.rolled + self.applied_modifier

    @property
    def calculation(self):
        dice = self.get_dice_display()
        if self.count > 1:
            dice = f"{self.count} × {dice}"
        results = " + ".join(str(result) for result in self.results)
        raw = f"{dice}: {results if self.results else self.rolled}"
        if not self.modifier:
            return f"{raw} = {self.total}" if len(self.results) > 1 else raw
        sign = "+" if self.modifier > 0 else "−"
        modifier = str(abs(self.modifier))
        if (
            self.count > 1
            and self.modifier_application == self.ModifierApplication.EACH
        ):
            modifier = f"({self.count} × {modifier})"
        return f"{raw} {sign} {modifier} = {self.total}"
