"""
Advancement models for content data.

This module contains:
- ContentAdvancementAssignment: Equipment configurations for advancements
- ContentAdvancementEquipment: Equipment-based advancements
"""

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from .base import Content


class ContentAdvancementAssignment(Content):
    """
    Represents a specific equipment configuration (with upgrades)
    that can be gained through advancement.
    """

    # Link to advancement equipment
    advancement = models.ForeignKey(
        "ContentAdvancementEquipment",
        on_delete=models.CASCADE,
        related_name="assignments",
        null=True,
        blank=True,
        help_text="The equipment advancement this assignment belongs to",
    )

    # The base equipment
    equipment = models.ForeignKey(
        "ContentEquipment",
        on_delete=models.CASCADE,
        related_name="advancement_assignments",
    )

    # Equipment upgrades
    upgrades_field = models.ManyToManyField(
        "ContentEquipmentUpgrade",
        blank=True,
        related_name="advancement_assignments",
        help_text="Upgrades that come with this equipment assignment",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Equipment Advancement Assignment"
        verbose_name_plural = "Equipment Advancement Assignments"
        ordering = ["advancement__name", "equipment__name"]

    def __str__(self):
        upgrade_names = ", ".join(
            str(upgrade.name) for upgrade in self.upgrades_field.all()
        )
        if upgrade_names:
            return f"{self.equipment} ({upgrade_names})"
        return str(self.equipment)


class ContentAdvancementEquipment(Content):
    """
    Defines advancements that allow a fighter to acquire equipment.

    Links equipment assignments to advancement costs and restrictions.
    """

    name = models.CharField(
        max_length=255,
        help_text="Name for this advancement (e.g., 'Legendary Name')",
    )

    xp_cost = models.PositiveIntegerField(
        help_text="XP cost to acquire this equipment through advancement"
    )

    cost_increase = models.IntegerField(
        default=0, help_text="Fighter cost increase when this equipment is gained"
    )

    # Restriction options
    restricted_to_houses = models.ManyToManyField(
        "ContentHouse",
        blank=True,
        related_name="advancement_equipment",
        help_text="If set, only these houses can gain this equipment via advancement",
    )

    restricted_to_fighter_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="List of fighter categories that can gain this equipment (e.g., ['GANGER', 'CHAMPION'])",
    )

    # Selection type flags
    enable_random = models.BooleanField(
        default=False, help_text="Allow random selection from the equipment list"
    )

    enable_chosen = models.BooleanField(
        default=False, help_text="Allow player to choose from the equipment list"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Equipment Advancement"
        verbose_name_plural = "Equipment Advancements"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}"

    def is_available_to_fighter(self, list_fighter):
        """Check if this advancement equipment is available to a specific fighter."""
        # Check house restrictions
        if self.restricted_to_houses.exists():
            if list_fighter.list.content_house not in self.restricted_to_houses.all():
                return False

        # Check fighter category restrictions
        if (
            self.restricted_to_fighter_categories
            and len(self.restricted_to_fighter_categories) > 0
        ):
            if (
                list_fighter.content_fighter.category
                not in self.restricted_to_fighter_categories
            ):
                return False

        return True

    def clean(self):
        """Validate that at least one selection type is enabled."""
        super().clean()
        if not self.enable_random and not self.enable_chosen:
            raise ValidationError(
                "At least one selection type (random or chosen) must be enabled."
            )
