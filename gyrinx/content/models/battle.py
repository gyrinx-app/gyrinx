"""
Battle role models for content data.

Uses a container/option structure so a "role" is a set of mutually exclusive
options that a battle participant can take:

- ContentBattleRole: a named role axis (e.g. "Attacker/Defender")
- ContentBattleRoleOption: a pickable option within a role (e.g. "Attacker")
"""

from django.db import models
from simple_history.models import HistoricalRecords

from .base import Content


class ContentBattleRole(Content):
    """
    A named set of battle participant roles (e.g. "Attacker/Defender").

    Acts as a container for the individual options a participant can be
    assigned. A scenario can later reference a role to constrain which options
    apply to a battle.
    """

    help_text = "A named set of battle participant roles, e.g. Attacker/Defender."
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Battle Role"
        verbose_name_plural = "Battle Roles"
        ordering = ["name"]


class ContentBattleRoleOption(Content):
    """
    A single role a participant can take within a ContentBattleRole
    (e.g. "Attacker" or "Defender").
    """

    help_text = "A role a participant can take in a battle, e.g. Attacker or Defender."
    role = models.ForeignKey(
        ContentBattleRole,
        on_delete=models.CASCADE,
        related_name="options",
        help_text="The battle role this option belongs to.",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.role.name}: {self.name}"

    class Meta:
        verbose_name = "Battle Role Option"
        verbose_name_plural = "Battle Role Options"
        ordering = ["role__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["role", "name"],
                name="unique_battle_role_option_name",
            )
        ]
