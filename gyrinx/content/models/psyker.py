##
## Content Models
##


from gyrinx.content.models.base import Content


from django.db import models
from simple_history.models import HistoricalRecords


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
