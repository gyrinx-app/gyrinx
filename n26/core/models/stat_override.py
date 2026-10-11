"""Characteristics an owner has set by hand on their own model.

A model's characteristics come from the profile it was hired from, then
rules adjust them. Sometimes neither matches the table: a campaign awards
an advance the library does not have, a group agrees a house change, or a
profile was entered differently from the book. An owner can then set a
characteristic directly.

There is one ``StatOverride`` per overridden characteristic and none for
the rest. Overriding Strength leaves every other characteristic following
the profile, including later author corrections.

The override replaces the **base** value, before computed effects apply: a
rule that improves Weapon Skill improves the owner's value, not the
profile's.

Overrides are not bought and do not change rating. They are part of the
gang's history, so they are written through ``Operation.set_stats``, which
records a journal event per change. Anything the gang's history should
show goes through an operation; device preferences (``AssignmentSet``,
``PrintConfig``) stay plain saves.
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
        """Store the value in its stat's canonical format.

        An owner typing 4 for Movement means 4", as an author's 4 does.
        Without this, the edit box and the card would show the value
        differently.
        """
        if self.value and self.statline_type_stat_id:
            self.value = self.statline_type_stat.stat.format_value(self.value)
        super().save(*args, **kwargs)
