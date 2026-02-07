"""
Roll table and flow models for content data.

This module contains:
- ContentRollTable: Dice table definition
- ContentRollTableRow: Individual results on a roll table
- ContentRollFlow: Links a counter to a roll table with a cost
"""

from django.db import models
from simple_history.models import HistoricalRecords

from .base import Content


class ContentRollTable(Content):
    """
    A dice table definition (e.g. "Power Boost Table").
    """

    help_text = "A dice table that fighters can roll on."

    DICE_D6 = "D6"
    DICE_D66 = "D66"
    DICE_2D6 = "2D6"
    DICE_CHOICES = [
        (DICE_D6, "D6"),
        (DICE_D66, "D66"),
        (DICE_2D6, "2D6"),
    ]

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    dice = models.CharField(
        max_length=10,
        choices=DICE_CHOICES,
        help_text="Dice configuration for this table.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Roll Table"
        verbose_name_plural = "Roll Tables"
        ordering = ["name"]


class ContentRollTableRow(Content):
    """
    An individual result row on a roll table.
    """

    help_text = "A single result on a roll table, with optional modifiers."

    table = models.ForeignKey(
        ContentRollTable,
        on_delete=models.CASCADE,
        related_name="rows",
        help_text="The roll table this row belongs to.",
    )
    roll_value = models.CharField(
        max_length=20,
        help_text='Dice result or range (e.g. "1", "2-3", "4-5", "6").',
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    modifiers = models.ManyToManyField(
        "ContentMod",
        blank=True,
        help_text="Modifiers applied when this result is gained.",
        related_name="roll_table_rows",
    )
    rating_increase = models.IntegerField(
        default=0,
        help_text="Rating increase when this result is gained.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering within the table.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.table.name}: {self.roll_value} - {self.name}"

    class Meta:
        verbose_name = "Roll Table Row"
        verbose_name_plural = "Roll Table Rows"
        ordering = ["table", "sort_order"]
        unique_together = [("table", "sort_order")]


class ContentRollFlow(Content):
    """
    Links a counter to a roll table, defining a "spend X, roll on Y" flow.
    """

    help_text = "Defines a flow: spend counter points to roll on a table."

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    counter = models.ForeignKey(
        "ContentCounter",
        on_delete=models.CASCADE,
        related_name="flows",
        help_text="Which counter to spend.",
    )
    cost = models.PositiveIntegerField(
        help_text="How many counter points to spend.",
    )
    roll_table = models.ForeignKey(
        ContentRollTable,
        on_delete=models.CASCADE,
        related_name="flows",
        help_text="Table to roll on.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Roll Flow"
        verbose_name_plural = "Roll Flows"
        ordering = ["name"]
