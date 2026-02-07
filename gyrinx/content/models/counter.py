"""
Counter models for content data.

This module contains:
- ContentCounter: Named counter that can be attached to specific content fighters
"""

from django.db import models
from simple_history.models import HistoricalRecords

from .base import Content


class ContentCounter(Content):
    """
    A named counter that can be attached to specific content fighters.

    Counters track numeric values per fighter (e.g. Kill Count, Glitch Count).
    The actual per-fighter values are stored in ListFighterCounter (core app).
    """

    help_text = "A named counter attached to specific fighter types."

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    restricted_to_fighters = models.ManyToManyField(
        "ContentFighter",
        blank=True,
        help_text="Which content fighters show this counter. If empty, no fighters show it.",
        related_name="counters",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Ordering on the fighter card (lower = first).",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Counter"
        verbose_name_plural = "Counters"
        ordering = ["display_order", "name"]
