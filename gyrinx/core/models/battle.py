from django.contrib.auth import get_user_model
from django.db import models
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase

User = get_user_model()


class Battle(AppBase):
    """
    Battle model to track battles that occur within a campaign.
    """

    campaign = models.ForeignKey(
        "core.Campaign",
        on_delete=models.CASCADE,
        related_name="battles",
        help_text="The campaign this battle belongs to",
        db_index=True,
    )
    date = models.DateField(
        help_text="The date the battle took place",
        db_index=True,
    )
    mission = models.CharField(
        max_length=200,
        help_text="The mission name or type",
    )
    participants = models.ManyToManyField(
        "core.List",
        related_name="battles_participated",
        help_text="Lists/gangs that participated in the battle",
    )
    winners = models.ManyToManyField(
        "core.List",
        related_name="battles_won",
        blank=True,
        help_text="Lists/gangs that won the battle (leave empty for draws)",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-date", "-created"]
        indexes = [
            models.Index(fields=["campaign", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return self.name

    @cached_property
    def name(self):
        """Computed name for the battle."""
        battle_number = (
            self.campaign.battles.filter(date__lt=self.date).count()
            + self.campaign.battles.filter(
                date=self.date, created__lt=self.created
            ).count()
            + 1
        )
        return f"{self.mission} {self.date} #{battle_number}"

    def can_edit(self, user):
        """
        Check if a user can edit this battle.
        Only the battle owner or campaign owner can edit.
        Cannot edit if campaign is archived.
        """
        if not user or not user.is_authenticated:
            return False
        if self.campaign.archived:
            return False
        return user == self.owner or user == self.campaign.owner

    def can_add_notes(self, user):
        """
        Check if a user can add notes to this battle.
        Participant gang owners can add notes.
        Cannot add notes if campaign is archived.
        """
        if not user or not user.is_authenticated:
            return False
        if self.campaign.archived:
            return False
        if self.can_edit(user):
            return True
        # Check if user owns any of the participant lists
        return self.participants.filter(owner=user).exists()

    def get_actions(self):
        """Get all campaign actions associated with this battle."""
        return self.campaign.actions.filter(battle=self)


class BattleNote(AppBase):
    """
    Notes added to a battle by different users.
    """

    battle = models.ForeignKey(
        Battle,
        on_delete=models.CASCADE,
        related_name="notes",
        help_text="The battle this note belongs to",
    )
    content = models.TextField(
        help_text="Note content (supports rich text formatting)",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["created"]
        indexes = [
            models.Index(fields=["battle", "created"]),
        ]

    def __str__(self):
        return f"Note by {self.owner} on {self.battle}"

    def can_edit(self, user):
        """
        Check if a user can edit this note.
        Only the note owner can edit their own notes.
        """
        if not user or not user.is_authenticated:
            return False
        return user == self.owner
