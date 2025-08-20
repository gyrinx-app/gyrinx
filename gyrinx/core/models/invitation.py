import logging

from django.contrib.auth import get_user_model
from django.core import validators
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase

logger = logging.getLogger(__name__)
User = get_user_model()


class CampaignInvitation(AppBase):
    """Invitation for a list to join a campaign."""

    # Status choices
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
    ]

    campaign = models.ForeignKey(
        "Campaign",
        on_delete=models.CASCADE,
        related_name="invitations",
        help_text="The campaign this invitation is for",
        db_index=True,
    )
    list = models.ForeignKey(
        "List",
        on_delete=models.CASCADE,
        related_name="campaign_invitations",
        help_text="The list being invited to the campaign",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=PENDING,
        help_text="Current status of the invitation",
        db_index=True,
    )
    message = models.TextField(
        blank=True,
        validators=[validators.MaxLengthValidator(500)],
        help_text="Optional message from the campaign owner",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Campaign Invitation"
        verbose_name_plural = "Campaign Invitations"
        ordering = ["-created"]
        unique_together = [("campaign", "list")]

    def __str__(self):
        return f"Invitation for {self.list.name} to join {self.campaign.name}"

    @property
    def is_pending(self):
        return self.status == self.PENDING

    @property
    def is_accepted(self):
        return self.status == self.ACCEPTED

    @property
    def is_declined(self):
        return self.status == self.DECLINED

    def accept(self):
        """Accept the invitation and add the list to the campaign."""
        if not self.is_pending:
            return False

        # Add the list to the campaign using existing method
        self.campaign.add_list_to_campaign(self.list)
        self.status = self.ACCEPTED
        self.save()
        return True

    def decline(self):
        """Decline the invitation."""
        if not self.is_pending:
            return False

        self.status = self.DECLINED
        self.save()
        return True
