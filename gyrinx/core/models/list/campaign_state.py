import logging

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import (
    Q,
)
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentAttributeValue,
    ContentSkillCategory,
    ContentStatlineTypeStat,
)
from gyrinx.core.models.base import AppBase
from gyrinx.core.models.list.fighter import ListFighter
from gyrinx.core.models.list.list import List
from gyrinx.models import (
    Archived,
    Base,
)

logger = logging.getLogger(__name__)
pylist = list


class ListFighterInjury(AppBase):
    """Track injuries for fighters in campaign mode."""

    help_text = "Tracks lasting injuries sustained by a fighter during campaign play."

    fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="injuries",
        help_text="The fighter who has sustained this injury.",
    )
    injury = models.ForeignKey(
        "content.ContentInjury",
        on_delete=models.CASCADE,
        help_text="The specific injury sustained.",
    )
    date_received = models.DateTimeField(
        auto_now_add=True,
        help_text="When this injury was sustained.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about how this injury was received.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-date_received"]
        verbose_name = "Fighter Injury"
        verbose_name_plural = "Fighter Injuries"

    def __str__(self):
        return f"{self.fighter.name} - {self.injury.name}"

    def clean(self):
        # Only allow injuries on campaign mode fighters
        if self.fighter.list.status != List.CAMPAIGN_MODE:
            raise ValidationError(
                "Injuries can only be added to fighters in campaign mode."
            )


class ListFighterCounter(AppBase):
    """Track counter values for fighters (e.g. Kill Count, Glitch Count).

    Created on-demand when the user first edits a counter value.
    The counter row is displayed on the fighter card by detecting that
    the fighter's content_fighter is in a ContentCounter.restricted_to_fighters set.
    """

    help_text = "Tracks the value of a counter for a specific fighter."

    fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="counters",
        help_text="The fighter this counter belongs to.",
    )
    counter = models.ForeignKey(
        "content.ContentCounter",
        on_delete=models.CASCADE,
        related_name="fighter_values",
        help_text="The counter definition.",
    )
    value = models.IntegerField(
        default=0,
        help_text="Current counter value.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["counter__display_order", "counter__name"]
        verbose_name = "Fighter Counter"
        verbose_name_plural = "Fighter Counters"
        unique_together = [("fighter", "counter")]

    def __str__(self):
        return f"{self.fighter.name} - {self.counter.name}: {self.value}"


class ListAttributeAssignment(Base, Archived):
    """
    Through model that links a List to ContentAttributeValues.
    """

    help_text = "Associates gang attributes (like Alignment, Alliance, Affiliation) with a list."

    list = models.ForeignKey(
        List,
        on_delete=models.CASCADE,
        help_text="The list this attribute is assigned to.",
    )
    attribute_value = models.ForeignKey(
        ContentAttributeValue,
        on_delete=models.CASCADE,
        help_text="The attribute value assigned to the list.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "List Attribute Assignment"
        verbose_name_plural = "List Attribute Assignments"
        unique_together = [["list", "attribute_value"]]

    def __str__(self):
        return f"{self.list.name} - {self.attribute_value.attribute.name}: {self.attribute_value.name}"

    def clean(self):
        """Validate that single-select attributes only have one value per list."""
        if self.attribute_value and self.list:
            attribute = self.attribute_value.attribute
            if attribute.is_single_select:
                # Check if there's already an assignment for this attribute
                existing = (
                    ListAttributeAssignment.objects.filter(
                        list=self.list,
                        attribute_value__attribute=attribute,
                        archived=False,  # Only check active assignments
                    )
                    .exclude(pk=self.pk)
                    .exists()
                )
                if existing:
                    raise ValidationError(
                        f"The attribute '{attribute.name}' is single-select and already has a value assigned to this list."
                    )


class ListSkillTreeAssignment(Base, Archived):
    """
    A gang-wide skill-tree pick: links a List to a ContentSkillCategory at a
    given ranked slot.

    Only meaningful for lists whose house has ``gang_wide_skills`` enabled. The
    ranked picks here are combined with the house's ``skill_rank_rules`` to
    derive each fighter's primary/secondary skill trees by rank.
    """

    help_text = "A ranked gang skill-tree choice for a list (gang-wide skills)."

    list = models.ForeignKey(
        List,
        on_delete=models.CASCADE,
        help_text="The list this skill-tree pick belongs to.",
    )
    slot = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text="1-based rank of this skill tree within the gang's selection.",
    )
    skill_category = models.ForeignKey(
        ContentSkillCategory,
        on_delete=models.CASCADE,
        help_text="The skill tree chosen for this slot.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "List Skill Tree Assignment"
        verbose_name_plural = "List Skill Tree Assignments"
        ordering = ["list", "slot"]
        constraints = [
            # Only one active pick per slot, and a given tree can't be picked
            # twice while active. Enforced in the form too, but guard the DB
            # against races / direct edits.
            models.UniqueConstraint(
                fields=["list", "slot"],
                condition=Q(archived=False),
                name="uniq_active_list_skill_tree_slot",
            ),
            models.UniqueConstraint(
                fields=["list", "skill_category"],
                condition=Q(archived=False),
                name="uniq_active_list_skill_tree_category",
            ),
        ]

    def __str__(self):
        return f"{self.list.name} — slot {self.slot}: {self.skill_category.name}"


class CapturedFighter(AppBase):
    """Tracks a fighter being held captive by another gang."""

    # The captured fighter
    fighter = models.OneToOneField(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="capture_info",
        help_text="The fighter who has been captured",
    )

    # The gang holding the fighter captive
    capturing_list = models.ForeignKey(
        List,
        on_delete=models.CASCADE,
        related_name="captured_fighters",
        help_text="The gang currently holding this fighter captive",
    )

    # When they were captured
    captured_at = models.DateTimeField(
        auto_now_add=True, help_text="When the fighter was captured"
    )

    # Track if sold to guilders
    sold_to_guilders = models.BooleanField(
        default=False, help_text="Whether the fighter has been sold to guilders"
    )
    sold_at = models.DateTimeField(
        null=True, blank=True, help_text="When the fighter was sold to guilders"
    )

    # Credits exchanged (if any)
    ransom_amount = models.IntegerField(
        null=True,
        blank=True,
        help_text="Credits paid as ransom or received for selling",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Captured Fighter"
        verbose_name_plural = "Captured Fighters"
        ordering = ["-captured_at"]

    def __str__(self):
        status = "sold to guilders" if self.sold_to_guilders else "captured"
        return f"{self.fighter.name} ({status} by {self.capturing_list.name})"

    def sell_to_guilders(self, credits=None):
        """Mark the fighter as sold to guilders."""
        from django.utils import timezone

        self.sold_to_guilders = True
        self.sold_at = timezone.now()
        if credits is not None:
            self.ransom_amount = credits
        self.save()

    def return_to_owner(self, credits=None):
        """Return the fighter to their original gang and delete the capture record."""
        if credits is not None:
            self.ransom_amount = credits
            self.save()

        # Delete the capture record, which returns the fighter to their original gang
        self.delete()

    def get_original_list(self):
        """Get the original gang this fighter belongs to."""
        return self.fighter.list


class ListFighterStatOverride(AppBase):
    """
    Allows overriding individual stat values for a ListFighter
    when they have a custom statline.
    """

    help_text = (
        "Represents a stat override for a ListFighter with a custom statline. "
        "This allows overriding individual stat values from the base ContentStatline."
    )

    list_fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        related_name="stat_overrides",
        help_text="The ListFighter this override applies to",
    )
    content_stat = models.ForeignKey(
        ContentStatlineTypeStat,
        on_delete=models.CASCADE,
        help_text="The stat being overridden",
    )
    value = models.CharField(
        max_length=10,
        help_text="The overridden stat value (e.g., '5\"', '12', '4+', '-')",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "List Fighter Stat Override"
        verbose_name_plural = "List Fighter Stat Overrides"
        unique_together = ["list_fighter", "content_stat"]
        ordering = ["content_stat__position"]

    def __str__(self):
        return (
            f"{self.list_fighter.name} - {self.content_stat.short_name}: {self.value}"
        )
