"""Private working reports and immutable receipts for one gang's battle results."""

from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from n26.core.models.abstract import Base


class PostBattleReport(Base):
    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPLIED = "applied", "Applied"

    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="post_battle_reports"
    )
    battle = models.ForeignKey(
        "n26.Battle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reports",
    )
    creator = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    last_editor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=200, blank=True)
    request_key = models.UUIDField()
    state = models.CharField(max_length=12, choices=State, default=State.DRAFT)
    draft = models.JSONField(default=dict, blank=True)
    generation = models.UUIDField(default=uuid4)
    draft_revision = models.PositiveIntegerField(default=0)
    latest_sequence = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-modified", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["gang", "battle"],
                condition=models.Q(battle__isnull=False),
                name="post_battle_once_per_gang",
            ),
            models.UniqueConstraint(
                fields=["gang", "request_key"], name="post_battle_start_once"
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=["draft", "applied"]),
                name="post_battle_state_known",
            ),
        ]

    def __str__(self):
        return self.reference or f"Post-battle report on {self.date}"


class PostBattleRevision(Base):
    """An application and its frozen names, effects and actual ledger movements."""

    report = models.ForeignKey(
        PostBattleReport, on_delete=models.CASCADE, related_name="revisions"
    )
    sequence = models.PositiveIntegerField()
    submission_key = models.UUIDField(unique=True)
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    batch = models.UUIDField(default=uuid4, unique=True)
    inputs = models.JSONField(default=dict)
    receipt = models.JSONField(default=dict)

    class Meta:
        ordering = ["-sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["report", "sequence"], name="post_battle_sequence_once"
            ),
            models.CheckConstraint(
                condition=models.Q(sequence__gt=0), name="post_battle_sequence_positive"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("An applied post-battle receipt cannot be edited.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Post-battle revision {self.sequence}"
