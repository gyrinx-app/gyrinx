import logging

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.content.models import (
    ContentPsykerPower,
)
from gyrinx.core.models.list.fighter import ListFighter
from gyrinx.models import (
    Archived,
    Base,
)

logger = logging.getLogger(__name__)
pylist = list


class ListFighterPsykerPowerAssignment(Base, Archived):
    """A ListFighterPsykerPowerAssignment is a link between a ListFighter and a Psyker Power."""

    help_text = "A ListFighterPsykerPowerAssignment is a link between a ListFighter and a Psyker Power."
    list_fighter = models.ForeignKey(
        ListFighter,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        verbose_name="Fighter",
        related_name="psyker_powers",
        help_text="The ListFighter that this psyker power assignment is linked to.",
    )
    psyker_power = models.ForeignKey(
        ContentPsykerPower,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        verbose_name="Psyker Power",
        related_name="list_fighters",
        help_text="The ContentSkill that this assignment is linked to.",
    )

    history = HistoricalRecords()

    def name(self):
        return f"{self.psyker_power.name} ({self.psyker_power.discipline})"

    def __str__(self):
        return f"{self.list_fighter} – {self.name()}"

    def clean(self):
        # TODO: Find a way to build this generically, rather than special-casing it
        if not self.list_fighter.is_psyker:
            raise ValidationError(
                {
                    "list_fighter": "You can't assign a psyker power to a fighter that is not a psyker."
                }
            )

        # Pack-aware: catch pack-authored default assignments too.
        from gyrinx.content.models.psyker import (
            ContentFighterPsykerPowerDefaultAssignment,
        )

        if (
            ContentFighterPsykerPowerDefaultAssignment.objects.with_packs(
                self.list_fighter.list.packs.all(), include_archived_items=True
            )
            .filter(
                fighter=self.list_fighter.content_fighter,
                psyker_power=self.psyker_power,
            )
            .exists()
        ):
            raise ValidationError(
                {
                    "psyker_power": "You can't assign a psyker power that is already assigned by default."
                }
            )

        # Check if the psyker power's discipline is available to this fighter
        available_disciplines = self.list_fighter.get_available_psyker_disciplines()
        if (
            not self.psyker_power.discipline.generic
            and self.psyker_power.discipline not in available_disciplines
        ):
            raise ValidationError(
                {
                    "psyker_power": "You can't assign a psyker power from a non-generic discipline if the fighter is not assigned that discipline."
                }
            )

    class Meta:
        verbose_name = "Fighter Psyker Power Assignment"
        verbose_name_plural = "Fighter Psyker Power Assignments"
        unique_together = ("list_fighter", "psyker_power")
