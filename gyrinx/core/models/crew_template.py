from django.core import validators
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase


class CrewTemplate(AppBase):
    """Template for selecting a crew from a list's fighters."""

    name = models.CharField(
        max_length=255,
        validators=[validators.MinLengthValidator(1)],
        help_text="Name for this crew template.",
    )

    list = models.ForeignKey(
        "List",
        on_delete=models.CASCADE,
        related_name="crew_templates",
        help_text="The list this crew template belongs to.",
    )

    # Selection methodology
    chosen_fighters = models.ManyToManyField(
        "ListFighter",
        blank=True,
        related_name="crew_templates",
        help_text="Specific fighters to include in the crew.",
    )

    random_count = models.PositiveIntegerField(
        default=0,
        validators=[validators.MaxValueValidator(20)],
        help_text="Number of additional random fighters to select from remaining active fighters (max 20).",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]
        verbose_name = "Crew Template"
        verbose_name_plural = "Crew Templates"

    def __str__(self):
        return f"{self.name} - {self.list.name}"

    def selection_summary(self):
        """Display a summary of the crew selection methodology."""
        parts = []
        chosen_count = self.chosen_fighters.count()
        if chosen_count > 0:
            parts.append(f"{chosen_count} chosen")
        if self.random_count > 0:
            parts.append(f"{self.random_count} random")
        if not parts:
            return "No fighters selected"
        return ", ".join(parts)
