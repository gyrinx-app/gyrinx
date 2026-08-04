"""
Attribute models for content data.

This module contains:
- ContentAttribute: Gang attributes (e.g., Alignment, Alliance, Affiliation)
- ContentAttributeValue: Allowed values for attributes
"""

from django.db import models
from simple_history.models import HistoricalRecords

from .base import Content


class ContentAttribute(Content):
    """
    Represents an attribute that can be associated with gangs/lists
    (e.g., Alignment, Alliance, Affiliation).
    """

    help_text = "Defines attributes that can be associated with gangs, such as Alignment, Alliance, or Affiliation."
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="The name of the attribute (e.g., 'Alignment', 'Alliance', 'Affiliation').",
    )
    is_single_select = models.BooleanField(
        default=True,
        help_text="If True, only one value can be selected. If False, multiple values can be selected.",
    )
    restricted_to = models.ManyToManyField(
        "ContentHouse",
        blank=True,
        related_name="restricted_attributes",
        verbose_name="Restricted To",
        help_text="If provided, this attribute is only available to specific gang houses.",
    )

    history = HistoricalRecords()

    def __str__(self):
        select_type = "single-select" if self.is_single_select else "multi-select"
        return f"{self.name} ({select_type})"

    class Meta:
        verbose_name = "Gang Attribute"
        verbose_name_plural = "Gang Attributes"
        ordering = ["name"]


class ContentAttributeValue(Content):
    """
    Represents allowed values for a ContentAttribute.
    """

    help_text = "Defines the allowed values for a gang attribute."
    attribute = models.ForeignKey(
        ContentAttribute,
        on_delete=models.CASCADE,
        related_name="values",
        help_text="The attribute this value belongs to.",
    )
    name = models.CharField(
        max_length=255,
        help_text="The value name (e.g., 'Law Abiding', 'Outlaw', 'Chaos Cult').",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional description of what this value represents.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Gang Attribute Value"
        verbose_name_plural = "Gang Attribute Values"
        ordering = ["attribute__name", "name"]
        unique_together = [["attribute", "name"]]
