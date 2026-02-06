from django.contrib import admin
from django.core import validators
from django.db import models
from django.utils.translation import ngettext
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase


class PrintConfig(AppBase):
    """Configuration for customizing print output of a list."""

    # Fighter selection mode choices
    ALL_FIGHTERS = "all"
    SPECIFIC_FIGHTERS = "specific"
    NO_FIGHTERS = "none"
    FIGHTER_SELECTION_CHOICES = [
        (ALL_FIGHTERS, "All current & future fighters"),
        (SPECIFIC_FIGHTERS, "Specific fighters"),
        (NO_FIGHTERS, "None"),
    ]

    name = models.CharField(
        max_length=255,
        validators=[validators.MinLengthValidator(1)],
        help_text="Name for this print configuration.",
    )

    list = models.ForeignKey(
        "List",
        on_delete=models.CASCADE,
        related_name="print_configs",
        help_text="The list this print configuration belongs to.",
    )

    # Card type toggles
    include_assets = models.BooleanField(
        default=True,
        help_text="Include asset card in the print output.",
    )

    include_attributes = models.BooleanField(
        default=True,
        help_text="Include attribute card in the print output.",
    )

    include_stash = models.BooleanField(
        default=True,
        help_text="Include the stash card in the print output.",
    )

    include_actions = models.BooleanField(
        default=False,
        help_text="Include the action card in the print output.",
    )

    include_dead_fighters = models.BooleanField(
        default=False,
        help_text="Include dead fighters in the print output.",
    )

    # Blank card options
    blank_fighter_cards = models.PositiveIntegerField(
        default=0,
        validators=[validators.MaxValueValidator(20)],
        help_text="Number of blank fighter cards to include (max 20).",
    )

    blank_vehicle_cards = models.PositiveIntegerField(
        default=0,
        validators=[validators.MaxValueValidator(20)],
        help_text="Number of blank vehicle/crew cards to include (max 20).",
    )

    # Fighter selection mode
    fighter_selection_mode = models.CharField(
        max_length=20,
        choices=FIGHTER_SELECTION_CHOICES,
        default=ALL_FIGHTERS,
        help_text="How to select which fighters to include in the print output.",
    )

    # Fighter selection - many-to-many relationship with ListFighter
    included_fighters = models.ManyToManyField(
        "ListFighter",
        blank=True,
        related_name="print_configs",
        help_text="Specific fighters to include in the print output.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]
        verbose_name = "Print Configuration"
        verbose_name_plural = "Print Configurations"

    def __str__(self):
        return f"{self.name} - {self.list.name}"

    @admin.display(description="Cards")
    def card_summary(self):
        """Display a summary of which card types are included."""
        included = []
        if self.include_assets:
            included.append("Assets")
        if self.include_attributes:
            included.append("Attributes")
        if self.include_stash:
            included.append("Stash")
        if self.include_actions:
            included.append("Actions")
        if self.include_dead_fighters:
            included.append("Dead Fighters")

        # Handle fighter selection based on mode
        if self.fighter_selection_mode == self.NO_FIGHTERS:
            included.append("No Fighters")
        elif self.fighter_selection_mode == self.SPECIFIC_FIGHTERS:
            fighter_count = self.included_fighters.count()
            if fighter_count > 0:
                included.append(
                    ngettext("%(count)d Fighter", "%(count)d Fighters", fighter_count)
                    % {"count": fighter_count}
                )
            else:
                included.append("0 Fighters")
        else:  # ALL_FIGHTERS
            included.append("All Fighters")

        if self.blank_fighter_cards > 0:
            included.append(
                ngettext(
                    "%(count)d Blank Fighter",
                    "%(count)d Blank Fighters",
                    self.blank_fighter_cards,
                )
                % {"count": self.blank_fighter_cards}
            )
        if self.blank_vehicle_cards > 0:
            included.append(
                ngettext(
                    "%(count)d Blank Vehicle",
                    "%(count)d Blank Vehicles",
                    self.blank_vehicle_cards,
                )
                % {"count": self.blank_vehicle_cards}
            )

        return ", ".join(included) if included else "None"
