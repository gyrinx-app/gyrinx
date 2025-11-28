from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.content.models.base import Content
from gyrinx.content.models.skill import ContentSkillCategory


class ContentHouse(Content):
    """
    Represents a faction or house that fighters can belong to.
    """

    help_text = "The Content House identifies the house or faction of a fighter."
    name = models.CharField(max_length=255, db_index=True)
    skill_categories = models.ManyToManyField(
        ContentSkillCategory,
        blank=True,
        related_name="houses",
        verbose_name="Unique Skill Categories",
    )
    generic = models.BooleanField(
        default=False,
        help_text="If checked, fighters in this House can join lists and gangs of any other House.",
    )
    legacy = models.BooleanField(
        default=False,
        help_text="If checked, this House is considered a legacy/older faction.",
    )
    can_hire_any = models.BooleanField(
        default=False,
        help_text="If checked, this House can hire any fighter from any house (except stash fighters).",
    )
    can_buy_any = models.BooleanField(
        default=False,
        help_text="If checked, this House can buy any equipment from any equipment list and trading post.",
    )

    history = HistoricalRecords()

    def fighters(self):
        """
        Returns all fighters associated with this house.
        """
        return self.contentfighter_set.all()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "House"
        verbose_name_plural = "Houses"
        ordering = ["name"]
