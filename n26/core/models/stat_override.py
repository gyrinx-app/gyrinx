"""Characteristics an owner has set on their own model, cell by cell.

A model's characteristics come from the entry it was hired from, and the
rules move them about from there. Sometimes neither is what is on the
table: a campaign hands out an advance nothing in the library carries, a
group agrees a change between themselves, an entry was typed differently
from the book. So an owner may set a characteristic themselves.

One row per cell they have taken over, and none for the cells they have
left alone — overriding a Strength therefore leaves the rest of the row
following the entry, including whatever an author corrects in it later.

What is set replaces the **base** value the card is drawn from, before
anything computed folds on top: a rule that improves a Weapon Skill
improves what the owner set, not what the entry prints.

Nothing here is bought, and setting a characteristic leaves what the
gang is worth alone — but it is part of the gang's story, so the rows
are written through ``Operation.set_stats`` and each change lands in
the history as a journal event. The line operations draw is the gang's
story, not only its money: what a reader of the gang's log would want
said goes through that one door, while device preferences
(``AssignmentSet``, ``PrintConfig``) stay plain saves.
"""

from django.db import models

from n26.core.models.abstract import Base


class StatOverride(Base):
    """One characteristic an owner has set by hand on one model."""

    miniature = models.ForeignKey(
        "n26.Miniature", on_delete=models.CASCADE, related_name="stat_overrides"
    )
    #: Which cell of the statline this stands in — the same row a library
    #: statline names, so an override and a printed value are values of
    #: the same thing and the shape they are drawn to is unchanged.
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
        """Store the value as its stat says it reads.

        An owner typing 4 for a Movement means 4", the same as an author
        typing it does, so the same canonical form is stored. Otherwise
        the box they type in and the card they are editing would print
        the value differently, with nothing to say which was meant.
        """
        if self.value and self.statline_type_stat_id:
            self.value = self.statline_type_stat.stat.format_value(self.value)
        super().save(*args, **kwargs)
