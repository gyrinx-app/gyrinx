"""A battle's saved model selection, separate from actual participation."""

from django.db import models

from n26.core.models.abstract import Base


class BattleCrew(Base):
    battle = models.ForeignKey(
        "n26.Battle", on_delete=models.CASCADE, related_name="crews"
    )
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="battle_crews"
    )
    revision = models.PositiveIntegerField(default=0)
    confirmed = models.BooleanField(default=False)
    draw_number = models.PositiveIntegerField(default=0)
    last_draw = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["battle", "gang"], name="one_crew_per_battle_gang"
            )
        ]


class CrewMember(Base):
    class Role(models.TextChoices):
        STARTING = "starting", "Starting crew"
        RESERVE = "reserve", "Reinforcements"

    class Source(models.TextChoices):
        MANUAL = "manual", "Chosen"
        RANDOM = "random", "Randomly selected"
        OVERRIDE = "override", "Card overridden"

    crew = models.ForeignKey(
        BattleCrew, on_delete=models.CASCADE, related_name="members"
    )
    miniature = models.ForeignKey(
        "n26.Miniature",
        on_delete=models.SET_NULL,
        null=True,
        related_name="crew_memberships",
    )
    miniature_name = models.CharField(max_length=200)
    role = models.CharField(max_length=12, choices=Role)
    source = models.CharField(max_length=12, choices=Source, default=Source.MANUAL)
    card_source = models.CharField(max_length=12, choices=Source, default=Source.MANUAL)
    eligibility_override = models.BooleanField(default=False)
    assignment_set = models.ForeignKey(
        "n26.AssignmentSet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crew_members",
    )
    card_name = models.CharField(max_length=200)
    # Plain IDs preserve the selection after a named card is edited or deleted.
    # They cannot restore equipment that has since left the model.
    equipment_ids = models.JSONField(default=list)
    rating = models.IntegerField(default=0)

    class Meta:
        ordering = ["miniature_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["crew", "miniature"], name="one_model_per_battle_crew"
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=["starting", "reserve"]),
                name="crew_member_valid_role",
            ),
        ]
