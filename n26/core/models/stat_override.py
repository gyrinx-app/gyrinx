"""Store owner overrides for individual model characteristics.

Each override replaces the profile's base value before computed effects
apply. Other cells continue using their profile values, including later
author corrections.

Overrides change no rating. Operation.set_stats writes them and journals
each change; display preferences such as AssignmentSet and PrintConfig
use plain saves.
"""

from django.db import models

from n26.core.models.abstract import Base


class StatOverride(Base):
    """One characteristic an owner has set by hand on one model."""

    miniature = models.ForeignKey(
        "n26.Miniature", on_delete=models.CASCADE, related_name="stat_overrides"
    )
    #: The statline characteristic this overrides. It is the same
    #: ``StatlineTypeStat`` a library statline uses, so an override and a
    #: profile value fill the same cell.
    statline_type_stat = models.ForeignKey(
        "library.StatlineTypeStat", on_delete=models.PROTECT, related_name="+"
    )
    #: As wide as a library statline cell, because it stands in for one.
    value = models.CharField(
        max_length=10, help_text="""The raw value, e.g. '5"', '12', '4+', '-'."""
    )

    class Meta:
        verbose_name = "stat override"
        verbose_name_plural = "stat overrides"
        ordering = ["statline_type_stat__position"]
        constraints = [
            models.UniqueConstraint(
                "miniature",
                "statline_type_stat",
                name="stat_override_unique_per_model",
            ),
        ]

    def __str__(self):
        return f"{self.miniature}: {self.statline_type_stat.short_name} {self.value}"

    def save(self, *args, **kwargs):
        """Store the characteristic in its stat's canonical format so the edit field and card display the same value."""
        if self.value and self.statline_type_stat_id:
            self.value = self.statline_type_stat.stat.format_value(self.value)
        super().save(*args, **kwargs)
