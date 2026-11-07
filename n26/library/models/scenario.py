"""The editable tables used to generate a battle scenario."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from n26.library.models.assignable import Family
from n26.library.models.base import Content

PRIMARY_KEYS = ("deployment", "objective", "crew")


class ScenarioTable(Content):
    """A D6 table of scenario components or a set of side jobs.

    Each table has six entries. New side-job sets are staged until their
    entries are complete. Editing live wording changes existing results too.
    """

    family = Family.BASE

    class Purpose(models.TextChoices):
        DEPLOYMENT = "deployment", "Deployment"
        OBJECTIVE = "objective", "Objective"
        CREW = "crew", "Crew"
        SIDE_JOB = "side_job", "Side jobs"

    name = models.CharField(max_length=200, help_text="The name players see.")
    purpose = models.CharField(
        max_length=16,
        choices=Purpose,
        default=Purpose.SIDE_JOB,
        help_text="The part of a scenario this table supplies.",
    )
    legacy_key = models.CharField(
        max_length=40, unique=True, null=True, blank=True, editable=False
    )
    position = models.PositiveIntegerField(
        default=0, help_text="Order in the side-job set menu."
    )

    class Meta:
        ordering = ["position", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["pack", "purpose"],
                condition=~models.Q(purpose="side_job"),
                name="scenario_primary_once_per_pack",
            )
        ]

    @property
    def key(self):
        return self.legacy_key or str(self.pk)

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.name.strip():
            raise ValidationError({"name": "Enter a table name."})
        if not self._state.adding:
            previous = type(self).objects.get(pk=self.pk)
            if (self.legacy_key, self.purpose, self.pack_id) != (
                previous.legacy_key,
                previous.purpose,
                previous.pack_id,
            ):
                raise ValidationError(
                    "A scenario table's identity, purpose and pack cannot change."
                )
        if self.purpose != self.Purpose.SIDE_JOB and (self.archived or self.staged):
            raise ValidationError("The generator's primary tables must remain live.")
        if self.pack.slug != settings.DEFAULT_CONTENT_PACK_SLUG:
            raise ValidationError("Scenario tables belong to the default content pack.")

    def check_complete(self):
        entries = list(self.entries.order_by("roll"))
        if [entry.roll for entry in entries] != list(range(1, 7)) or any(
            not entry.name.strip()
            or not entry.text.strip()
            or entry.archived
            or entry.staged
            for entry in entries
        ):
            raise ValidationError(
                "Complete all six D6 entries before previewing or putting this table live."
            )
        return entries


class ScenarioEntry(Content):
    """One named result on a scenario table, with its description and diagram.

    The result number stays fixed so saved scenarios keep the same entry.
    Asterisks around words display them in bold.
    """

    table = models.ForeignKey(
        ScenarioTable, on_delete=models.PROTECT, related_name="entries"
    )
    roll = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="The D6 result, from 1 to 6. This cannot change after creation.",
    )
    name = models.CharField(max_length=200, help_text="The result's name.")
    text = models.TextField(
        verbose_name="description",
        help_text="What this result means. Put asterisks around words to display them in bold.",
    )
    image = models.CharField(max_length=500, blank=True, default="", editable=False)
    diagram = models.ImageField(
        upload_to="n26/scenario-diagrams/",
        blank=True,
        default="",
        help_text="An optional PNG, JPEG or WebP diagram. Upload a new file to replace it.",
    )
    diagram_alt = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="diagram description",
        help_text="Describe the diagram for players who cannot see it.",
    )

    class Meta:
        ordering = ["table", "roll"]
        constraints = [
            models.UniqueConstraint(
                fields=["table", "roll"], name="scenario_entry_once_per_roll"
            ),
            models.CheckConstraint(
                condition=models.Q(roll__gte=1, roll__lte=6),
                name="scenario_entry_d6_result",
            ),
        ]

    def __str__(self):
        return f"{self.roll}. {self.name}"

    def clean(self):
        super().clean()
        if self.table_id and self.pack_id != self.table.pack_id:
            raise ValidationError("An entry belongs to its table's pack.")
        if self.staged or self.archived:
            raise ValidationError(
                "Stage or retire the whole scenario table instead of an entry."
            )
        if not self.name.strip() or not self.text.strip():
            raise ValidationError("Enter a name and description for this result.")
        if self.text.count("*") % 2:
            raise ValidationError({"text": "Close each bold passage with an asterisk."})
        if self.diagram and not self.diagram_alt.strip():
            raise ValidationError({"diagram_alt": "Describe the diagram."})
        if not self._state.adding:
            previous = type(self).objects.get(pk=self.pk)
            if (self.table_id, self.roll, self.pack_id) != (
                previous.table_id,
                previous.roll,
                previous.pack_id,
            ):
                raise ValidationError(
                    "An entry's table, result number and pack cannot change."
                )
