from django.contrib import admin
from django.core import validators
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase


class PrintConfig(AppBase):
    """Configuration for customizing print output of a list."""

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
        help_text="Include asset cards in the print output.",
    )

    include_attributes = models.BooleanField(
        default=True,
        help_text="Include attribute cards in the print output.",
    )

    include_stash = models.BooleanField(
        default=True,
        help_text="Include stash cards in the print output.",
    )

    include_actions = models.BooleanField(
        default=False,
        help_text="Include action cards in the print output.",
    )

    include_dead_fighters = models.BooleanField(
        default=False,
        help_text="Include dead fighters in the print output.",
    )

    # Fighter selection - many-to-many relationship with ListFighter
    included_fighters = models.ManyToManyField(
        "ListFighter",
        blank=True,
        related_name="print_configs",
        help_text="Specific fighters to include in the print output.",
    )

    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the default configuration for the list.",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-is_default", "name"]
        verbose_name = "Print Configuration"
        verbose_name_plural = "Print Configurations"
        constraints = [
            # Only one default config per list
            models.UniqueConstraint(
                fields=["list", "is_default"],
                condition=models.Q(is_default=True),
                name="unique_default_print_config_per_list",
            )
        ]

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
        return ", ".join(included) if included else "None"

    def save(self, *args, **kwargs):
        # If this is being set as default, unset any other defaults for this list
        if self.is_default and self.list_id:
            PrintConfig.objects.filter(list=self.list, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)
        super().save(*args, **kwargs)
