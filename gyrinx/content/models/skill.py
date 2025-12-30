"""
Skill models for content data.

This module contains:
- ContentSkillCategory: Skill trees/categories
- ContentSkill: Individual skills within categories
"""

from django.db import models
from simple_history.models import HistoricalRecords

from .base import Content


class ContentSkillCategory(Content):
    """
    Represents a category of skills that fighters may possess.
    """

    name = models.CharField(max_length=255, unique=True)
    restricted = models.BooleanField(
        default=False,
        help_text="If checked, this skill tree is only available to specific gangs.",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Skill Tree"
        verbose_name_plural = "Skill Trees"
        ordering = ["name"]


class ContentSkill(Content):
    """
    Represents a skill that fighters may possess.
    """

    name = models.CharField(max_length=255, db_index=True)
    category = models.ForeignKey(
        ContentSkillCategory,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="skills",
        verbose_name="tree",
        db_index=True,
    )
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.name}"

    class Meta:
        verbose_name = "Skill"
        verbose_name_plural = "Skills"
        ordering = ["category", "name"]
        unique_together = ["name", "category"]
