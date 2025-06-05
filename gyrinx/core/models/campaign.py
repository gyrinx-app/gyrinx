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
        """Start the campaign (transition from pre-campaign to in-progress).

        This will clone all associated lists into campaign mode.
        """
        if self.can_start_campaign():
            # Clone all lists for the campaign
            original_lists = list(self.lists.all())
            self.lists.clear()  # Remove the original lists

            for original_list in original_lists:
                # Clone the list for campaign mode
                campaign_clone = original_list.clone(for_campaign=self)
                self.lists.add(campaign_clone)

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


class CampaignAssetType(AppBase):
    """Type of asset that can be held in a campaign (e.g., Territory, Relic)"""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="asset_types",
        help_text="The campaign this asset type belongs to",
    )
    name_singular = models.CharField(
        max_length=100,
        help_text="Singular form of the asset type name (e.g., 'Territory')",
        validators=[validators.MinLengthValidator(1)],
    )
    name_plural = models.CharField(
        max_length=100,
        help_text="Plural form of the asset type name (e.g., 'Territories')",
        validators=[validators.MinLengthValidator(1)],
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this asset type",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Campaign Asset Type"
        verbose_name_plural = "Campaign Asset Types"
        unique_together = [("campaign", "name_singular")]
        ordering = ["name_singular"]

    def __str__(self):
        return f"{self.campaign.name} - {self.name_singular}"


class CampaignAsset(AppBase):
    """An asset that can be held by a list in a campaign"""

    asset_type = models.ForeignKey(
        CampaignAssetType,
        on_delete=models.CASCADE,
        related_name="assets",
        help_text="The type of this asset",
    )
    name = models.CharField(
        max_length=200,
        help_text="Name of the asset (e.g., 'The Sump')",
        validators=[validators.MinLengthValidator(1)],
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this asset",
    )
    holder = models.ForeignKey(
        "List",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="held_assets",
        help_text="The list currently holding this asset",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Campaign Asset"
        verbose_name_plural = "Campaign Assets"
        ordering = ["asset_type", "name"]

    def __str__(self):
        return f"{self.name} ({self.asset_type.name_singular})"

    def transfer_to(self, new_holder, user):
        """Transfer this asset to a new holder and log the action

        Args:
            new_holder: The List that will hold this asset (can be None)
            user: The User performing the transfer (required)
        """
        if not user:
            raise ValueError("User is required for asset transfers")

        old_holder = self.holder
        self.holder = new_holder
        self.save_with_user(user=user)

        # Create action log entry
        if old_holder or new_holder:
            old_name = old_holder.name if old_holder else "no one"
            new_name = new_holder.name if new_holder else "no one"
            description = f"{self.asset_type.name_singular} Transfer: {self.name} transferred from {old_name} to {new_name}"

            CampaignAction.objects.create(
                campaign=self.asset_type.campaign,
                user=user,
                description=description,
                dice_count=0,
            )
