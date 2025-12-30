"""
Psyker models for content data.

This module contains:
- ContentPsykerDiscipline: Psyker disciplines
- ContentPsykerPower: Individual psyker powers
- ContentFighterPsykerDisciplineAssignment: Fighter-discipline assignments
- ContentFighterPsykerPowerDefaultAssignment: Default power assignments for fighters
"""

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from .base import Content


class ContentPsykerDiscipline(Content):
    """
    Represents a discipline of Psyker/Wyrd powers.
    """

    name = models.CharField(max_length=255, unique=True)
    generic = models.BooleanField(
        default=False,
        help_text="If checked, this discipline can be used by any psyker.",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Psyker Discipline"
        verbose_name_plural = "Psyker Disciplines"
        ordering = ["name"]


class ContentPsykerPower(Content):
    """
    Represents a specific power within a discipline of Psyker/Wyrd powers.
    """

    name = models.CharField(max_length=255)
    discipline = models.ForeignKey(
        ContentPsykerDiscipline,
        on_delete=models.CASCADE,
        related_name="powers",
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Psyker Power"
        verbose_name_plural = "Psyker Powers"
        ordering = ["discipline__name", "name"]
        unique_together = ["name", "discipline"]


class ContentFighterPsykerDisciplineAssignment(Content):
    """
    Represents a discipline assignment for a Psyker content fighter.
    """

    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        related_name="psyker_disciplines",
    )
    discipline = models.ForeignKey(
        ContentPsykerDiscipline,
        on_delete=models.CASCADE,
        related_name="fighter_assignments",
    )
    history = HistoricalRecords()

    def clean(self):
        """
        Validation to ensure that a generic discipline cannot be assigned to a fighter.
        """
        # This is removed because fighters can *become* psykers later in the game, if a rule
        # is added via an updgrade or other means.
        # if not self.fighter.is_psyker:
        #     raise ValidationError(
        #         {
        #             "fighter": "Cannot assign a psyker discipline to a non-psyker fighter."
        #         }
        #     )

        if self.discipline.generic:
            raise ValidationError(
                {
                    "discipline": "Cannot assign a generic psyker discipline to a fighter."
                }
            )

    def __str__(self):
        return f"{self.fighter} {self.discipline}"

    class Meta:
        verbose_name = "Fighter Psyker Discipline"
        verbose_name_plural = "Fighter Psyker Disciplines"
        unique_together = ["fighter", "discipline"]
        ordering = ["fighter__type", "discipline__name"]


class ContentFighterPsykerPowerDefaultAssignment(Content):
    """
    Represents a default power assignment for a Psyker content fighter.
    """

    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        related_name="default_psyker_powers",
    )
    psyker_power = models.ForeignKey(
        ContentPsykerPower,
        on_delete=models.CASCADE,
        related_name="fighter_assignments",
    )
    history = HistoricalRecords()

    def clean_fields(self, exclude={}):
        """
        Validation to ensure that defaults cannot be assigned to a non-Psyker fighter.
        """
        if "fighter" not in exclude and not self.fighter.is_psyker:
            raise ValidationError(
                {"fighter": "Cannot assign a psyker power to a non-psyker fighter."}
            )

    def name(self):
        return f"{self.psyker_power.name} ({self.psyker_power.discipline})"

    def __str__(self):
        return f"{self.fighter} {self.psyker_power}"

    class Meta:
        verbose_name = "Psyker Fighter-Power Default Assignment"
        verbose_name_plural = "Psyker Fighter-Power Default Assignments"
        unique_together = ["fighter", "psyker_power"]
        ordering = ["fighter__type", "psyker_power__name"]
