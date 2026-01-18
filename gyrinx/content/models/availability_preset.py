"""
Availability preset models for content data.

This module contains:
- ContentAvailabilityPreset: Configurable availability defaults for fighters/categories/houses
"""

from django.db import models
from django.db.models import Case, IntegerField, Q, Value, When
from multiselectfield import MultiSelectField
from simple_history.models import HistoricalRecords

from gyrinx.models import FighterCategoryChoices

from .base import Content


AVAILABILITY_CHOICES = [
    ("C", "Common (C)"),
    ("R", "Rare (R)"),
    ("I", "Illegal (I)"),
    ("E", "Exclusive (E)"),
    ("U", "Unique (U)"),
]


class ContentAvailabilityPreset(Content):
    """
    Preset availability filters for equipment browsing.

    Defines default availability types and max level for specific
    fighter/category/house combinations. More specific presets
    (more fields matched) take precedence.

    Used by houses with can_buy_any=True to provide sensible defaults
    when browsing the Trading Post.

    Examples:
        - Fighter-specific: fighter=Goliath Leader, category=null, house=null
        - Category+House: fighter=null, category=LEADER, house=Goliath
        - Category only: fighter=null, category=LEADER, house=null
        - House only: fighter=null, category=null, house=Goliath
    """

    help_text = "Preset availability filters for equipment browsing based on fighter, category, or house."

    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="availability_presets",
        help_text="Specific fighter this preset applies to (most specific match)",
    )

    category = models.CharField(
        max_length=50,
        choices=FighterCategoryChoices.choices,
        null=True,
        blank=True,
        db_index=True,
        help_text="Fighter category this preset applies to",
    )

    house = models.ForeignKey(
        "ContentHouse",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="availability_presets",
        help_text="House this preset applies to",
    )

    availability_types = MultiSelectField(
        choices=AVAILABILITY_CHOICES,
        default=["C", "R"],
        help_text="Availability types to show by default (C/R/I/E/U)",
    )

    max_availability_level = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum availability level (rarity roll). Leave blank for no limit.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Availability Preset"
        verbose_name_plural = "Availability Presets"
        ordering = ["-created"]
        unique_together = ["fighter", "category", "house"]

    def __str__(self):
        """Human-readable representation showing which fields are matched."""
        parts = []

        if self.fighter:
            parts.append(f"Fighter: {self.fighter.type}")
        if self.category:
            parts.append(f"Category: {self.get_category_display()}")
        if self.house:
            parts.append(f"House: {self.house.name}")

        if not parts:
            parts.append("Default (global)")

        descriptor = " + ".join(parts)
        types = (
            ", ".join(self.availability_types) if self.availability_types else "none"
        )

        level_str = (
            f", max level {self.max_availability_level}"
            if self.max_availability_level
            else ""
        )

        return f"{descriptor}: [{types}{level_str}]"

    @property
    def availability_types_list(self) -> list:
        """Return availability types as a list."""
        if isinstance(self.availability_types, str):
            return self.availability_types.split(",") if self.availability_types else []
        return list(self.availability_types) if self.availability_types else []

    @classmethod
    def get_preset_for(cls, fighter, category, house):
        """
        Get the most specific preset for a fighter, category, and house combination.

        Matching logic:
        - A preset matches if ALL its non-null fields match the input
        - Specificity = count of non-null fields in the preset
        - Most specific (highest count) wins
        - Ties broken by most recently created

        Args:
            fighter: ContentFighter instance (or None)
            category: Fighter category string from FighterCategoryChoices (or None)
            house: ContentHouse instance (or None)

        Returns:
            ContentAvailabilityPreset or None if no match found
        """
        # Build filter: each preset field must be NULL OR match input
        q_filter = Q()

        if fighter is not None:
            q_filter &= Q(fighter=fighter) | Q(fighter__isnull=True)
        else:
            q_filter &= Q(fighter__isnull=True)

        if category is not None:
            q_filter &= Q(category=category) | Q(category__isnull=True)
        else:
            q_filter &= Q(category__isnull=True)

        if house is not None:
            q_filter &= Q(house=house) | Q(house__isnull=True)
        else:
            q_filter &= Q(house__isnull=True)

        # Annotate with specificity (count of non-null fields)
        preset = (
            cls.objects.filter(q_filter)
            .annotate(
                specificity=Case(
                    When(fighter__isnull=False, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
                + Case(
                    When(category__isnull=False, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
                + Case(
                    When(house__isnull=False, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
            .order_by("-specificity", "-created")
            .first()
        )

        return preset

    def clean(self):
        """Validate the preset configuration."""
        from django.core.exceptions import ValidationError

        super().clean()

        # Validate max_availability_level is positive if set
        if self.max_availability_level is not None and self.max_availability_level < 1:
            raise ValidationError(
                {
                    "max_availability_level": "Maximum availability level must be at least 1"
                }
            )
