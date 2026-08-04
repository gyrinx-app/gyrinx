"""
Gang-wide skill models for content data.

This module contains:
- ContentHouseSkillRankAccess: per-house rule mapping a fighter rank (category)
  to which ranked gang skill-tree slots are primary/secondary.

These rules are only consulted for houses with ``gang_wide_skills`` enabled. A
gang of such a house picks a ranked set of skill trees (stored on the list as
``ListSkillTreeAssignment``); each fighter then derives its primary/secondary
skill trees from these rules based on its rank.
"""

from django.core.validators import MinValueValidator
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.models import FighterCategoryChoices

from .base import Content


class ContentHouseSkillRankAccess(Content):
    """
    Maps a fighter rank (category) to a ranked gang skill-tree slot and role.

    One row means: "in this House, a fighter of category ``fighter_category``
    gets the skill tree the gang ranked at ``slot`` as ``role``
    (primary or secondary)."
    """

    help_text = (
        "For a Gang-wide-skills House, maps a fighter rank to which ranked gang "
        "skill-tree slot is primary/secondary."
    )

    PRIMARY = "primary"
    SECONDARY = "secondary"
    ROLE_CHOICES = [
        (PRIMARY, "Primary"),
        (SECONDARY, "Secondary"),
    ]

    house = models.ForeignKey(
        "ContentHouse",
        on_delete=models.CASCADE,
        related_name="skill_rank_rules",
        help_text="The House this rule applies to.",
    )
    fighter_category = models.CharField(
        max_length=255,
        choices=FighterCategoryChoices.choices,
        help_text="The fighter rank this rule applies to.",
    )
    slot = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text="1-based rank of the gang skill tree this rule refers to.",
    )
    role = models.CharField(
        max_length=16,
        choices=ROLE_CHOICES,
        help_text="Whether the tree at this slot is primary or secondary for this rank.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "House Skill Rank Rule"
        verbose_name_plural = "House Skill Rank Rules"
        ordering = ["house__name", "fighter_category", "slot"]
        unique_together = ["house", "fighter_category", "slot"]

    def __str__(self):
        return f"{self.house.name} — {self.fighter_category} slot {self.slot} ({self.role})"
