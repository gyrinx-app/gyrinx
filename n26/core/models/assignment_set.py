"""Assignment sets — the rulebook's multiple Model Cards.

A model owns one pool of equipment, bought once and counted once. An
assignment set is a **named selection** from that pool: which weapons and
wargear show on one particular card. The rulebook calls these equipment
sets — "all models can have multiple Model Cards, each representing a
different set of equipment".

The default card is **no set at all**: building a card without a set means
everything the model owns, which is what the code always did.

What is selectable is hard-coded for now: weapons and wargear hosted on the
model. Everything else — the profile, subtypes, skills, injuries — rides
every card ("If the model suffers any Lasting Injuries… it should be
recorded on all of their Model Cards"). A weapon's ammo follows the weapon.

Sets are free, change no rating and touch no ledger — pure
display state, so they do not go through ``n26.operations``.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from n26.core.models.abstract import Base

#: Assignment columns a set may select. Everything else is always on-card.
SELECTABLE_FIELDS = ("weapon", "wargear")


class AssignmentSet(Base):
    miniature = models.ForeignKey(
        "n26.Miniature", on_delete=models.CASCADE, related_name="assignment_sets"
    )
    name = models.CharField(max_length=200)
    assignments = models.ManyToManyField(
        "n26.Assignment",
        blank=True,
        related_name="assignment_sets",
        help_text=(
            "The model's equipment shown on this card. Equipment not listed "
            "is hidden on this card but stays owned."
        ),
    )

    class Meta:
        verbose_name = "assignment set"
        verbose_name_plural = "assignment sets"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "miniature", Lower("name"), name="assignment_set_unique_per_model"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.miniature})"

    def validate_assignments(self):
        """Every selected assignment must be this model's own equipment.

        Not ``clean()``: M2M rows can only be checked once both sides exist.
        Call after editing the selection.
        """
        problems = []
        for assignment in self.assignments.all():
            if assignment.miniature_id != self.miniature_id:
                problems.append(f"{assignment} is not on {self.miniature}")
            elif all(
                getattr(assignment, f"{field}_id") is None
                for field in SELECTABLE_FIELDS
            ):
                problems.append(
                    f"{assignment} is not equipment — only weapons and wargear "
                    f"can vary between cards"
                )
        if problems:
            raise ValidationError(problems)

    def selected_ids(self):
        return set(self.assignments.values_list("pk", flat=True))
