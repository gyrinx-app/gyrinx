"""
Statline models for content data.

This module contains:
- ContentStat: Stat definitions (e.g., Movement, Toughness)
- ContentStatlineType: Types of statlines (e.g., Fighter, Vehicle)
- ContentStatlineTypeStat: Links stats to statline types with positioning
- ContentStatline: Actual stat values for a fighter
- ContentStatlineStat: Individual stat values within a statline
"""

from django.core.exceptions import ValidationError
from django.db import models
from multiselectfield import MultiSelectField
from simple_history.models import HistoricalRecords

from gyrinx.models import FighterCategoryChoices

from .base import Content


class ContentStat(Content):
    """
    Represents a single stat definition that can be used across multiple
    statline types. This avoids duplication of stat definitions.
    """

    help_text = "A stat definition that can be shared across different statline types."
    field_name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal field name (e.g., 'movement', 'front_toughness')",
    )
    short_name = models.CharField(
        max_length=10, help_text="Short display name (e.g., 'M', 'Fr')"
    )
    full_name = models.CharField(
        max_length=50,
        help_text="Full display name (e.g., 'Movement', 'Front Toughness')",
    )
    is_inverted = models.BooleanField(
        default=False,
        help_text='If inverted, "improving" this stat means decreasing the number e.g. Cool 4+ to 3+',
    )
    is_inches = models.BooleanField(
        default=False,
        help_text='This stat represents a distance measured in inches and gets a quote-mark when displayed e.g. Movement 3"',
    )
    is_modifier = models.BooleanField(
        default=False,
        help_text="This stat modifies a roll and gets a plus prefix when displayed, e.g. Acc S +3",
    )
    is_target = models.BooleanField(
        default=False,
        help_text="This stat is a target of a roll and gets a plus suffix when displayed, e.g. WS 3+",
    )

    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Auto-generate field_name from full_name on first save
        if not self.field_name and self.full_name:
            import re

            # Convert to lowercase and replace non-alphanumeric with underscores
            field_name = re.sub(r"[^a-z0-9]+", "_", self.full_name.lower())
            # Remove leading/trailing underscores
            field_name = field_name.strip("_")
            # Replace multiple underscores with single
            field_name = re.sub(r"_+", "_", field_name)
            self.field_name = field_name

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.short_name} ({self.full_name})"

    class Meta:
        verbose_name = "Stat"
        verbose_name_plural = "Stats"
        ordering = ["full_name"]


class ContentStatlineType(Content):
    """
    Defines a type of statline (e.g., 'Fighter', 'Vehicle') that can have
    different sets of statistics.
    """

    help_text = "Represents a type of statline with its own set of stats (e.g., Fighter, Vehicle)."
    name = models.CharField(max_length=255, unique=True)
    default_for_categories = MultiSelectField(
        choices=FighterCategoryChoices.choices,
        blank=True,
        help_text="Fighter categories that default to this statline type when created in content packs.",
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Statline Type"
        verbose_name_plural = "Statline Types"
        ordering = ["name"]


class ContentStatlineTypeStat(Content):
    """
    Links a stat to a statline type with display properties.
    This allows the same stat to be used across multiple statline types
    with different positions and display settings.
    """

    help_text = "Links a stat definition to a statline type with positioning and display settings."
    statline_type = models.ForeignKey(
        ContentStatlineType, on_delete=models.CASCADE, related_name="stats"
    )
    stat = models.ForeignKey(
        ContentStat, on_delete=models.CASCADE, related_name="statline_type_stats"
    )
    position = models.IntegerField(
        help_text="Display order position (lower numbers appear first)"
    )
    is_highlighted = models.BooleanField(
        default=False,
        help_text="Whether this stat should be highlighted in the UI (like Ld, Cl, Wil, Int)",
    )
    is_first_of_group = models.BooleanField(
        default=False,
        help_text="Whether this stat starts a new visual group (adds border)",
    )

    history = HistoricalRecords()

    # Properties for backward compatibility
    @property
    def field_name(self):
        return self.stat.field_name

    @property
    def short_name(self):
        return self.stat.short_name

    @property
    def full_name(self):
        return self.stat.full_name

    def __str__(self):
        return f"{self.statline_type.name} - {self.stat.short_name} ({self.stat.full_name})"

    class Meta:
        verbose_name = "Statline Type Stat"
        verbose_name_plural = "Statline Type Stats"
        ordering = ["statline_type", "position"]
        unique_together = ["statline_type", "stat"]


class ContentStatline(Content):
    """
    Stores actual stat values for a ContentFighter using a flexible statline type.
    """

    help_text = (
        "Stores the actual stat values for a fighter using a custom statline type."
    )
    content_fighter = models.OneToOneField(
        "ContentFighter", on_delete=models.CASCADE, related_name="custom_statline"
    )
    statline_type = models.ForeignKey(ContentStatlineType, on_delete=models.CASCADE)

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.content_fighter} - {self.statline_type.name} Statline"

    def clean(self):
        """
        Validates that all required stats have values through ContentStatlineStat.

        Note: This validation is skipped during creation since the related
        ContentStatlineStat objects are created after the ContentStatline is saved.
        The admin's save_related method handles creating missing stats automatically.
        """
        # Only validate if this is an existing object (has a pk) and has a statline type
        # Skip validation during creation or when pk is not yet set
        if (
            self.statline_type_id
            and self.pk
            and hasattr(self, "_state")
            and not self._state.adding
        ):
            required_stats = set(
                self.statline_type.stats.values_list("stat__field_name", flat=True)
            )

            # Only validate if there are required stats
            if required_stats:
                provided_stats = set(
                    self.stats.values_list(
                        "statline_type_stat__stat__field_name", flat=True
                    )
                )
                missing_stats = required_stats - provided_stats

                if missing_stats:
                    raise ValidationError(
                        f"Missing required stats: {', '.join(sorted(missing_stats))}"
                    )

    class Meta:
        verbose_name = "Fighter Statline"
        verbose_name_plural = "Fighter Statlines"


class ContentStatlineStat(Content):
    """
    Stores a single stat value for a ContentStatline.
    """

    help_text = "Stores a single stat value for a fighter's statline."
    statline = models.ForeignKey(
        ContentStatline, on_delete=models.CASCADE, related_name="stats"
    )
    statline_type_stat = models.ForeignKey(
        ContentStatlineTypeStat, on_delete=models.CASCADE
    )
    value = models.CharField(
        max_length=10,
        help_text="The stat value (e.g., '5\"', '12', '4+', '-')",
    )

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.statline_type_stat.short_name}: {self.value}"

    class Meta:
        verbose_name = "Statline Stat"
        verbose_name_plural = "Statline Stats"
        unique_together = ["statline", "statline_type_stat"]
        ordering = ["statline_type_stat__position"]
