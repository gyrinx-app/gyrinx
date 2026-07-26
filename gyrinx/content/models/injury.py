"""
Injury models for content data.

This module contains:
- ContentInjuryDefaultOutcome: Enum for default fighter states after injury
- ContentInjuryGroup: Groups of related injuries
- ContentInjury: Individual injury definitions
- ContentEquipmentInjuryLink: Ties equipment to the injuries it treats
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


class ContentEquipmentInjuryLink(Content):
    """
    Ties an item of equipment to an injury it treats.

    Necromunda has two different ways for gear to answer a lasting injury, and
    the difference matters to the statline:

    - Trading Post bionics grant a flat +1 to a characteristic, "negating part
      or all of the effect" of the injury. The injury itself stays on the
      roster and its modifiers stay live — the two cancel out. That is
      ``OFFSET``, and it needs no arithmetic from us because the equipment
      already carries its own ``ContentMod``.
    - Van Saar Archaeo-Cyberteknika instead *replace* the injury's effects with
      the implant's own (which are rules, not stats — immunity to Insane,
      always-on infra-sight, and so on). Nothing offsets the penalty, so the
      injury's modifiers have to stop applying. That is ``SUPPRESS``.

    In both cases the injury is still a permanent note on the gang roster, so
    this link never deletes a :model:`core.ListFighterInjury` — it only marks
    it as treated, and in ``SUPPRESS`` mode drops its modifiers. Keeping the
    row is also what makes the "bionics damaged by a fresh injury to the same
    location" rule expressible later: it needs to know which injury a fitted
    implant belongs to.
    """

    help_text = "Marks an item of equipment as treating a particular injury."

    class Mode(models.TextChoices):
        OFFSET = "offset", "Offset (injury effects still apply)"
        SUPPRESS = "suppress", "Suppress (injury effects stop applying)"

    equipment = models.ForeignKey(
        # By name: ContentEquipment lives in equipment.py, which this module is
        # not imported by. ``injury`` below can use the class directly.
        "ContentEquipment",
        on_delete=models.CASCADE,
        related_name="injury_links",
        help_text="The equipment that treats the injury.",
    )
    injury = models.ForeignKey(
        ContentInjury,
        on_delete=models.CASCADE,
        related_name="treated_by",
        help_text="The injury this equipment treats.",
    )
    mode = models.CharField(
        max_length=10,
        choices=Mode.choices,
        default=Mode.OFFSET,
        help_text=(
            "Offset: the equipment's own modifiers cancel the injury, which "
            "keeps applying (Trading Post bionics). Suppress: the injury's "
            "modifiers stop applying entirely (Van Saar Cyberteknika)."
        ),
    )
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.equipment} treats {self.injury}"

    class Meta:
        verbose_name = "Equipment Injury Link"
        verbose_name_plural = "Equipment Injury Links"
        ordering = ["injury__name", "equipment__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["equipment", "injury"],
                name="uniq_equipment_injury_link",
            ),
        ]
