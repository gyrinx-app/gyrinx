import logging
import random

from django.contrib.auth import get_user_model
from django.core import validators
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase

logger = logging.getLogger(__name__)
User = get_user_model()


class Campaign(AppBase):
    # Status choices
    PRE_CAMPAIGN = "pre_campaign"
    IN_PROGRESS = "in_progress"
    POST_CAMPAIGN = "post_campaign"

    STATUS_CHOICES = [
        (PRE_CAMPAIGN, "Pre-Campaign"),
        (IN_PROGRESS, "In Progress"),
        (POST_CAMPAIGN, "Post-Campaign"),
    ]

    name = models.CharField(
        max_length=255, validators=[validators.MinLengthValidator(3)]
    )
    public = models.BooleanField(
        default=True, help_text="Public Campaigns are visible to all users."
    )
    summary = models.TextField(
        blank=True,
        validators=[validators.MaxLengthValidator(300)],
        help_text="A short summary of the campaign. This will be displayed on the campaign list page.",
    )
    narrative = models.TextField(
        blank=True,
        help_text="A longer narrative of the campaign. This will be displayed on the campaign detail page.",
    )
    lists = models.ManyToManyField(
        "List",
        blank=True,
        help_text="Lists that are part of this campaign.",
        related_name="campaigns",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=PRE_CAMPAIGN,
        help_text="Current status of the campaign.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Campaign"
        verbose_name_plural = "Campaigns"
        ordering = ["-created"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("core:campaign", args=[str(self.id)])

    @property
    def is_pre_campaign(self):
        return self.status == self.PRE_CAMPAIGN

    @property
    def is_in_progress(self):
        return self.status == self.IN_PROGRESS

    @property
    def is_post_campaign(self):
        return self.status == self.POST_CAMPAIGN

    def can_start_campaign(self):
        """Check if the campaign can be started."""
        return self.status == self.PRE_CAMPAIGN and self.lists.exists()

    def can_end_campaign(self):
        """Check if the campaign can be ended."""
        return self.status == self.IN_PROGRESS

    def start_campaign(self):
        """Start the campaign (transition from pre-campaign to in-progress)."""
        if self.can_start_campaign():
            self.status = self.IN_PROGRESS
            self.save()
            return True
        return False

    def end_campaign(self):
        """End the campaign (transition from in-progress to post-campaign)."""
        if self.can_end_campaign():
            self.status = self.POST_CAMPAIGN
            self.save()
            return True
        return False


class CampaignAction(AppBase):
    """An action taken during a campaign with optional dice rolls"""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="actions",
        help_text="The campaign this action belongs to",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="campaign_actions",
        help_text="The user who performed this action",
    )
    description = models.TextField(
        help_text="Description of the action taken",
        validators=[validators.MinLengthValidator(1)],
    )
    outcome = models.TextField(
        blank=True, help_text="Optional outcome or result of the action"
    )

    # Dice roll fields
    dice_count = models.PositiveIntegerField(
        default=0, help_text="Number of D6 dice rolled (0 if no roll)"
    )
    dice_results = models.JSONField(
        default=list, blank=True, help_text="Results of each die rolled"
    )
    dice_total = models.PositiveIntegerField(
        default=0, help_text="Total sum of all dice rolled"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Campaign Action"
        verbose_name_plural = "Campaign Actions"
        ordering = ["-created"]  # Most recent first

    def __str__(self):
        return f"{self.user.username}: {self.description[:50]}..."

    def roll_dice(self):
        """Roll the specified number of D6 dice and store results"""
        if self.dice_count > 0:
            self.dice_results = [random.randint(1, 6) for _ in range(self.dice_count)]
            self.dice_total = sum(self.dice_results)
        else:
            self.dice_results = []
            self.dice_total = 0

    def save(self, *args, **kwargs):
        # If dice_count is set but no results yet, roll the dice
        if self.dice_count > 0 and not self.dice_results:
            self.roll_dice()
        super().save(*args, **kwargs)
