"""Actions and rank tables: authored capabilities a fighter may hold and use."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from n26.core.constraints import exactly_one_of
from n26.library.models.assignable import (
    Assignable,
    Family,
    UsableBy,
    exclusive_has_no_trade_points,
)
from n26.library.models.base import Content


class RankTable(Content, Assignable):
    """A counter progression schedule assigned to a fighter."""

    family = Family.MODEL
    counter = models.ForeignKey(
        "library.Counter", on_delete=models.PROTECT, related_name="rank_tables"
    )

    class Meta:
        verbose_name = "rank table"
        verbose_name_plural = "rank tables"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="rank_table_unique_per_pack",
            ),
            exclusive_has_no_trade_points("rank_table"),
        ]

    def __str__(self):
        return self.name


class RankThreshold(Content):
    """One positive counter threshold in a rank table."""

    rank_table = models.ForeignKey(
        RankTable, on_delete=models.CASCADE, related_name="thresholds"
    )
    threshold = models.PositiveIntegerField(
        help_text="Counter value at which this action use is earned."
    )

    class Meta:
        ordering = ["rank_table", "threshold"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(threshold__gt=0), name="rank_threshold_positive"
            ),
            models.UniqueConstraint(
                "rank_table", "threshold", name="rank_threshold_unique_per_table"
            ),
        ]

    def __str__(self):
        return f"{self.rank_table}: {self.threshold}"


class RecruitmentAllowanceRule(Content):
    """Earn one use of an action when recruitment completes."""

    family = Family.FOUNDATION

    quantity = models.PositiveSmallIntegerField(default=1, editable=False)

    class Meta:
        verbose_name = "recruitment allowance rule"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity=1),
                name="recruitment_allowance_quantity_one",
            )
        ]


class RankAllowanceRule(Content):
    """Earn uses when an increase crosses thresholds in the effective rank table."""

    family = Family.FOUNDATION

    counter = models.ForeignKey(
        "library.Counter", on_delete=models.PROTECT, related_name="rank_allowance_rules"
    )

    class Meta:
        verbose_name = "rank allowance rule"


class Action(Content, Assignable, UsableBy):
    """A capability a fighter may use at recruitment or after a cycle."""

    family = Family.MODEL

    class Subject(models.TextChoices):
        FIGHTER = "fighter", "fighter"

    class Timing(models.TextChoices):
        RECRUITMENT = "recruitment", "recruitment"
        POST_CYCLE = "post_cycle", "after a cycle"

    subject = models.CharField(max_length=20, choices=Subject, default=Subject.FIGHTER)
    timing = models.CharField(max_length=20, choices=Timing)
    recruitment_allowance_rule = models.OneToOneField(
        RecruitmentAllowanceRule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action",
    )
    rank_allowance_rule = models.OneToOneField(
        RankAllowanceRule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="action_unique_per_pack",
            ),
            exclusive_has_no_trade_points("action"),
            models.CheckConstraint(
                condition=models.Q(recruitment_allowance_rule__isnull=True)
                | models.Q(rank_allowance_rule__isnull=True),
                name="action_at_most_one_allowance_rule",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def allowance_rule(self):
        return self.recruitment_allowance_rule or self.rank_allowance_rule

    def clean(self):
        super().clean()
        if self.recruitment_allowance_rule_id and self.rank_allowance_rule_id:
            raise ValidationError("An action can have only one allowance rule.")
        if self.allowance_rule and self.pk and self.use_price.exists():
            raise ValidationError(
                "An action with an allowance rule cannot also have a use price."
            )


class Outcome(Content):
    """A named result an action may produce, with one typed operation."""

    family = Family.FOUNDATION

    name = models.CharField(max_length=200)
    augment_carried_item = models.OneToOneField(
        "library.AugmentCarriedItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="outcome",
    )
    resolve_advancement = models.OneToOneField(
        "library.ResolveAdvancement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="outcome",
    )
    apply_changes = models.OneToOneField(
        "library.ApplyChanges",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="outcome",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack", Lower("name"), name="outcome_unique_per_pack"
            ),
            models.CheckConstraint(
                condition=exactly_one_of(
                    ("augment_carried_item", "resolve_advancement", "apply_changes")
                ),
                name="outcome_exactly_one_operation",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def operation(self):
        return (
            self.augment_carried_item or self.resolve_advancement or self.apply_changes
        )


class ActionOutcome(Content):
    """One possible outcome of an action, in display order."""

    action = models.ForeignKey(
        Action, on_delete=models.CASCADE, related_name="outcomes"
    )
    outcome = models.ForeignKey(
        Outcome, on_delete=models.PROTECT, related_name="actions"
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["action", "position", "created"]
        constraints = [
            models.UniqueConstraint(
                "action", "outcome", name="action_outcome_listed_once"
            )
        ]


class ActionPriceComponent(Content):
    """One required part of the price paid to use an action."""

    class Resource(models.TextChoices):
        CREDITS = "credits", "credits"
        COUNTER = "counter", "counter"

    class Payer(models.TextChoices):
        GANG = "gang", "gang"
        FIGHTER = "fighter", "fighter"

    action = models.ForeignKey(
        Action, on_delete=models.CASCADE, related_name="use_price"
    )
    resource = models.CharField(max_length=20, choices=Resource)
    payer = models.CharField(max_length=20, choices=Payer)
    counter = models.ForeignKey(
        "library.Counter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action_price_components",
    )
    amount = models.PositiveIntegerField()
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["action", "position", "created"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="action_price_amount_positive"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(resource="credits", payer="gang", counter__isnull=True)
                    | models.Q(resource="counter", counter__isnull=False)
                ),
                name="action_price_resource_is_complete",
            ),
        ]


class AugmentCarriedItem(Content):
    """Replace the current tier on one carried item with its next tier."""

    family = Family.FOUNDATION

    slot_type = models.ForeignKey(
        "library.SlotType",
        on_delete=models.PROTECT,
        related_name="augmentation_outcomes",
    )


class ResolveAdvancement(Content):
    """Roll on and resolve one advancement slot."""

    family = Family.FOUNDATION

    slot = models.ForeignKey(
        "library.Slot", on_delete=models.PROTECT, related_name="advancement_outcomes"
    )


class ApplyChanges(Content):
    """Apply each configured change in order as one outcome."""

    family = Family.FOUNDATION


class CounterChange(Content):
    """Set, add to or subtract from one fighter counter."""

    family = Family.FOUNDATION

    class Mode(models.TextChoices):
        SET = "set", "set"
        ADD = "add", "add"
        SUBTRACT = "subtract", "subtract"

    counter = models.ForeignKey(
        "library.Counter", on_delete=models.PROTECT, related_name="action_changes"
    )
    mode = models.CharField(max_length=20, choices=Mode)
    amount = models.IntegerField(default=0)


class RemovePicks(Content):
    """Remove every live pick of one slot type held by the fighter."""

    family = Family.FOUNDATION

    slot_type = models.ForeignKey(
        "library.SlotType", on_delete=models.PROTECT, related_name="remove_pick_changes"
    )


class ApplyChange(Content):
    """One typed change in an apply-changes outcome, in execution order."""

    apply_changes = models.ForeignKey(
        ApplyChanges, on_delete=models.CASCADE, related_name="changes"
    )
    counter_change = models.OneToOneField(
        CounterChange,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="applied_as",
    )
    remove_picks = models.OneToOneField(
        RemovePicks,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="applied_as",
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["apply_changes", "position", "created"]
        constraints = [
            models.CheckConstraint(
                condition=exactly_one_of(("counter_change", "remove_picks")),
                name="apply_change_exactly_one_change",
            )
        ]

    @property
    def change(self):
        return self.counter_change or self.remove_picks
