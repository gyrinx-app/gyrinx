"""Durable battle-save receipts shared by HTML and JSON adapters."""

from django.core.exceptions import ValidationError
from django.db import models

from n26.core.models.abstract import Base


class BattleCommand(Base):
    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="battle_commands"
    )
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    battle = models.ForeignKey(
        "n26.Battle", on_delete=models.RESTRICT, related_name="commands"
    )
    request_key = models.UUIDField()
    kind = models.CharField(max_length=10)
    inputs = models.JSONField(default=dict)
    revision = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "request_key"], name="battle_command_once"
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("A saved battle command cannot be edited.")
        return super().save(*args, **kwargs)
