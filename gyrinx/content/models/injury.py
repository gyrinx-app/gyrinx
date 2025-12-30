"""
Injury models for content data.

This module contains:
- ContentInjuryDefaultOutcome: Enum for default fighter states after injury
- ContentInjuryGroup: Groups of related injuries
- ContentInjury: Individual injury definitions
"""

from django.db import models
from multiselectfield import MultiSelectField
from simple_history.models import HistoricalRecords

from gyrinx.models import FighterCategoryChoices

from .base import Content


class ContentInjuryDefaultOutcome(models.TextChoices):
    """Default fighter state outcomes when injuries are applied"""

    NO_CHANGE = "no_change", "No Change"
    ACTIVE = "active", "Active"
    RECOVERY = "recovery", "Recovery"
    CONVALESCENCE = "convalescence", "Convalescence"
    DEAD = "dead", "Dead"
    IN_REPAIR = "in_repair", "In Repair"


class ContentInjuryGroup(Content):
    """
    Represents a group of injuries that can be applied to specific fighter categories.
    """

    help_text = (
        "Groups injuries and specifies which fighter categories can receive them."
    )
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    restricted_to = MultiSelectField(
        choices=FighterCategoryChoices.choices,
        blank=True,
        help_text="If set, only these fighter categories can receive injuries from this group.",
    )
    unavailable_to = MultiSelectField(
        choices=FighterCategoryChoices.choices,
        blank=True,
        help_text="If set, these fighter categories cannot receive injuries from this group.",
    )
    restricted_to_house = models.ManyToManyField(
        "ContentHouse",
        blank=True,
        help_text="If set, only these houses can use injuries from this group.",
        related_name="injury_groups",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Injury Group"
        verbose_name_plural = "Injury Groups"
        ordering = ["name"]


class ContentInjury(Content):
    """
    Named injuries that can be applied to fighters during campaigns.
    """

    help_text = "Represents a lasting injury that can be suffered by a fighter during campaign play."
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    phase = models.CharField(
        max_length=20,
        choices=ContentInjuryDefaultOutcome.choices,
        default=ContentInjuryDefaultOutcome.NO_CHANGE,
        help_text="The default fighter state outcome when this injury is applied.",
        verbose_name="Default Outcome",
    )
    injury_group = models.ForeignKey(
        ContentInjuryGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The injury group this injury belongs to.",
        related_name="injuries",
    )
    # Temporary: keep the old group field for migration purposes
    group = models.CharField(
        max_length=100,
        blank=True,
        help_text="(Deprecated) Text-based grouping for organizing injuries.",
    )
    modifiers = models.ManyToManyField(
        "ContentMod",
        blank=True,
        help_text="Modifiers applied when this injury is active.",
        related_name="injuries",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Injury"
        verbose_name_plural = "Injuries"
        ordering = ["injury_group__name", "name"]
