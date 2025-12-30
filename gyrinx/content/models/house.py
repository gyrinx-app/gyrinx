"""
House models for content data.

This module contains:
- ContentHouse: Factions/houses that fighters can belong to
- ContentFighterHouseOverride: House-specific fighter cost overrides
"""

from django.db import models
from simple_history.models import HistoricalRecords

from .base import Content


class ContentHouse(Content):
    """
    Represents a faction or house that fighters can belong to.
    """

    help_text = "The Content House identifies the house or faction of a fighter."
    name = models.CharField(max_length=255, db_index=True)
    skill_categories = models.ManyToManyField(
        "ContentSkillCategory",
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


class ContentFighterHouseOverride(Content):
    """
    Captures cases where a fighter has specific modifications (i.e. cost) when being added to
    a specific house.
    """

    fighter = models.ForeignKey(
        "ContentFighter",
        on_delete=models.CASCADE,
        db_index=True,
        related_name="house_overrides",
    )
    house = models.ForeignKey(
        ContentHouse,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="fighter_overrides",
    )
    cost = models.IntegerField(
        null=True,
        blank=True,
        help_text="What should this Fighter cost when added to this House?",
    )

    class Meta:
        verbose_name = "Fighter-House Override"
        verbose_name_plural = "Fighter-House Overrides"
        ordering = ["house__name", "fighter__type"]
        unique_together = ["fighter", "house"]

    def __str__(self):
        return f"{self.fighter} for {self.house}"

    def set_dirty(self) -> None:
        """Mark all ListFighters dirty that are affected by this house cost override.

        When a house override cost changes, ListFighters of this fighter type
        in lists belonging to this house need to be marked dirty.
        """
        from django.db.models import Q

        from gyrinx.core.models.list import ListFighter

        list_fighters = ListFighter.objects.filter(
            Q(content_fighter=self.fighter) | Q(legacy_content_fighter=self.fighter),
            list__content_house=self.house,
            archived=False,
        ).select_related("list")

        for list_fighter in list_fighters:
            list_fighter.set_dirty(save=True)
