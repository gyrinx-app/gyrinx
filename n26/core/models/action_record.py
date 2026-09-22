"""Durable records of fighter actions and the selections they produced.

An action assignment is access. These records are player history, so they do
not hang from that assignment's cause chain and survive when access changes.
Library references use labels to preserve the library-to-core dependency
direction described in ``n26/AGENTS.md``.
"""

from django.core.exceptions import ValidationError
from django.db import models

from n26.core.models.abstract import Base


class ActionAllowance(Base):
    """One earned use of an action, tied to the model's membership."""

    class Source(models.TextChoices):
        RECRUITMENT = "recruitment", "Recruitment"
        RANK = "rank", "Rank"

    action = models.ForeignKey(
        "library.Action", on_delete=models.PROTECT, related_name="allowances"
    )
    fighter = models.ForeignKey(
        "n26.Miniature", on_delete=models.CASCADE, related_name="action_allowances"
    )
    source = models.ForeignKey(
        "n26.Assignment", on_delete=models.CASCADE, related_name="action_allowances"
    )
    source_kind = models.CharField(max_length=20, choices=Source)
    threshold = models.PositiveIntegerField(null=True, blank=True)
    rank_table = models.ForeignKey(
        "library.RankTable",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="allowances",
    )
    granted_event = models.ForeignKey(
        "n26.LedgerEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_allowances",
    )

    class Meta:
        verbose_name = "action allowance"
        verbose_name_plural = "action allowances"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        source_kind="recruitment",
                        threshold__isnull=True,
                        rank_table__isnull=True,
                    )
                    | models.Q(
                        source_kind="rank",
                        threshold__isnull=False,
                        threshold__gt=0,
                        rank_table__isnull=False,
                    )
                ),
                name="action_allowance_source_is_whole",
            ),
            models.UniqueConstraint(
                fields=["action", "source"],
                condition=models.Q(source_kind="recruitment"),
                name="action_allowance_recruitment_once",
            ),
            models.UniqueConstraint(
                fields=["action", "source", "threshold"],
                condition=models.Q(source_kind="rank"),
                name="action_allowance_rank_once",
            ),
        ]

    def clean(self):
        super().clean()
        if self.fighter_id and self.source_id:
            if self.fighter.membership_id != self.source_id:
                raise ValidationError(
                    {"source": "The source must be this model's recruitment."}
                )


class ActionRecord(Base):
    """One started, completed or cancelled use of an assignable action."""

    class State(models.TextChoices):
        STARTED = "started", "Started"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="action_records"
    )
    fighter = models.ForeignKey(
        "n26.Miniature", on_delete=models.CASCADE, related_name="action_records"
    )
    action = models.ForeignKey(
        "library.Action", on_delete=models.PROTECT, related_name="records"
    )
    allowance = models.ForeignKey(
        ActionAllowance,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="records",
    )
    outcome = models.ForeignKey(
        "library.Outcome",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="records",
    )
    request_key = models.UUIDField()
    state = models.CharField(
        max_length=20, choices=State, default=State.STARTED, db_index=True
    )
    revision = models.PositiveIntegerField(default=0)
    source_assignment = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_action_records",
    )
    source = models.JSONField(default=dict, blank=True)
    review = models.JSONField(default=dict, blank=True)
    terms = models.JSONField(default=dict, blank=True)
    payment_id = models.UUIDField(null=True, blank=True, unique=True)
    started_event = models.ForeignKey(
        "n26.LedgerEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_action_records",
    )
    completed_event = models.ForeignKey(
        "n26.LedgerEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_action_records",
    )

    class Meta:
        verbose_name = "action record"
        verbose_name_plural = "action records"
        ordering = ["created"]
        constraints = [
            models.UniqueConstraint(
                fields=["gang", "request_key"], name="action_record_request_once"
            ),
            models.UniqueConstraint(
                fields=["allowance"],
                condition=models.Q(state__in=["started", "completed"]),
                name="action_record_reserves_allowance_once",
            ),
        ]

    def clean(self):
        super().clean()
        if self.fighter_id and self.gang_id:
            membership = self.fighter.membership
            if membership is None or membership.gang_id != self.gang_id:
                raise ValidationError(
                    {"fighter": "This model belongs to another gang."}
                )
        if self.allowance_id:
            errors = {}
            if self.allowance.fighter_id != self.fighter_id:
                errors["allowance"] = "This allowance belongs to another model."
            elif self.allowance.action_id != self.action_id:
                errors["allowance"] = "This allowance belongs to another action."
            if errors:
                raise ValidationError(errors)


class SlotSelection(Base):
    """The slot and exact picks recorded for an action, with an optional item."""

    action_record = models.OneToOneField(
        ActionRecord, on_delete=models.CASCADE, related_name="slot_selection"
    )
    item_assignment = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="action_item_selections",
    )
    slot_assignment = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="action_slot_selections",
    )
    previous_pick = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="action_previous_picks",
    )
    intended_pick = models.ForeignKey(
        "library.Pickable",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="intended_slot_selections",
    )
    new_pick = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="action_new_picks",
    )


class AdvancementSelection(Base):
    """The recorded roll and exact assignments for one advancement."""

    action_record = models.OneToOneField(
        ActionRecord, on_delete=models.CASCADE, related_name="advancement_selection"
    )
    promotion = models.ForeignKey(
        "library.AdvancementPromotion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="selections",
    )
    promotion_assignment = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="action_promotions",
    )
    slot_assignment = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="action_advancement_slots",
    )
    roll_event = models.ForeignKey(
        "n26.LedgerEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advancement_selections",
    )
    intended_pick = models.ForeignKey(
        "library.Pickable",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="intended_action_advancements",
    )
    pick_assignment = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="action_advancement_picks",
    )


class SkillSelection(Base):
    """The selection mode, access, skill set and final skill for an advancement."""

    class Mode(models.TextChoices):
        SELECT = "select", "Select"
        RANDOM = "random", "Random"

    class Access(models.TextChoices):
        PRIMARY = "primary", "Primary"
        SECONDARY = "secondary", "Secondary"
        ANY = "any", "Any"

    action_record = models.OneToOneField(
        ActionRecord, on_delete=models.CASCADE, related_name="skill_selection"
    )
    mode = models.CharField(max_length=20, choices=Mode)
    access = models.CharField(max_length=20, choices=Access)
    skill_set = models.ForeignKey(
        "library.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action_skill_selections",
    )
    selected_skill = models.ForeignKey(
        "library.Skill",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action_skill_results",
    )
    skill_assignment = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="action_skill_assignments",
    )
    random_attempts = models.JSONField(default=list, blank=True)
