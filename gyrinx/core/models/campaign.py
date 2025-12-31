import logging
import random

from django.contrib.auth import get_user_model
from django.core import validators
from django.db import models, transaction
from simple_history.models import HistoricalRecords

from gyrinx.core.models.base import AppBase

logger = logging.getLogger(__name__)
User = get_user_model()

pylist = list  # Alias for type hinting JSONField to use list type


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
        default=True,
        help_text="Public Campaigns are visible to all users.",
        db_index=True,
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
        db_index=True,
    )
    budget = models.PositiveIntegerField(
        default=1500,
        help_text="Starting budget for each gang in credits.",
    )
    phase = models.CharField(
        max_length=100,
        blank=True,
        help_text="Current campaign phase (e.g., 'Occupation', 'Takeover', 'Dominion')",
    )
    phase_notes = models.TextField(
        blank=True,
        help_text="Notes about the current phase - special rules, conditions, etc.",
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

    def can_reopen_campaign(self):
        """Check if the campaign can be reopened."""
        return self.status == self.POST_CAMPAIGN

    def _distribute_budget_to_list(self, campaign_list):
        """Distribute budget credits to a list based on campaign budget and list cost.

        Args:
            campaign_list: The List to distribute budget credits to
        """
        if self.budget > 0:
            # Calculate credits to give: max(0, budget - list cost)
            list_cost = campaign_list.cost_int() - campaign_list.credits_current
            credits_to_add = max(0, self.budget - list_cost)

            if credits_to_add > 0:
                campaign_list.credits_current += credits_to_add
                campaign_list.credits_earned += credits_to_add
                campaign_list.save()

                # Log the credit distribution as a campaign action
                CampaignAction.objects.create(
                    campaign=self,
                    user=self.owner,
                    list=campaign_list,
                    description=f"Campaign starting budget: Received {credits_to_add}¢ ({self.budget}¢ budget - {list_cost}¢ gang rating)",
                    outcome=f"+{credits_to_add}¢ (to {campaign_list.credits_current}¢)",
                    owner=self.owner,
                )

    def has_clone_of_list(self, original_list):
        """Check if the campaign already has a clone of the given list.

        Args:
            original_list: The original list to check for clones

        Returns:
            bool: True if a clone exists, False otherwise
        """
        return self.lists.filter(original_list=original_list).exists()

    def start_campaign(self):
        """Start the campaign (transition from pre-campaign to in-progress).

        This will clone all associated lists into campaign mode and allocate default resources.
        """
        if self.can_start_campaign():
            with transaction.atomic():
                # Clone all lists for the campaign
                # Only process lists that are not already campaign clones
                from .list import List

                original_lists = list(self.lists.filter(status=List.LIST_BUILDING))
                self.lists.clear()  # Remove all lists

                cloned_lists = []
                for original_list in original_lists:
                    # Check if we already have a clone of this list
                    # Note: We need to search in all lists, not just campaign.lists
                    # because we just cleared the campaign.lists
                    existing_clone = List.objects.filter(
                        original_list=original_list,
                        campaign=self,
                        status=List.CAMPAIGN_MODE,
                    ).first()

                    if existing_clone:
                        logger.warning(
                            f"Campaign {self.id} already has a clone of list {original_list.id}, re-adding existing clone"
                        )
                        # Re-add the existing clone to the campaign
                        self.lists.add(existing_clone)
                        cloned_lists.append(existing_clone)
                        continue

                    # Clone the list for campaign mode
                    campaign_clone = original_list.clone(for_campaign=self)
                    self.lists.add(campaign_clone)
                    cloned_lists.append(campaign_clone)

                    # Distribute budget credits to each gang
                    self._distribute_budget_to_list(campaign_clone)

                # Allocate default resources to each list
                for resource_type in self.resource_types.all():
                    for cloned_list in cloned_lists:
                        CampaignListResource.objects.get_or_create(
                            campaign=self,
                            resource_type=resource_type,
                            list=cloned_list,
                            defaults={
                                "amount": resource_type.default_amount,
                                "owner": self.owner,  # Campaign owner owns the resource tracking
                            },
                        )

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

    def reopen_campaign(self):
        """Reopen the campaign (transition from post-campaign back to in-progress)."""
        if self.can_reopen_campaign():
            self.status = self.IN_PROGRESS
            self.save()
            return True
        return False

    def add_list_to_campaign(self, list_to_add):
        """Add a list to the campaign, cloning if necessary.

        For pre-campaign: adds the list directly.
        For in-progress: clones the list and allocates resources.

        Returns a tuple (list, was_added) where:
        - list is the added list (original for pre-campaign, clone for in-progress)
        - was_added is True if the list was newly added, False if it already existed
        """
        if self.is_pre_campaign:
            # Pre-campaign: check if list is already in campaign
            if list_to_add in self.lists.all():
                return list_to_add, False
            # Add the list directly
            self.lists.add(list_to_add)
            return list_to_add, True
        elif self.is_in_progress:
            with transaction.atomic():
                # Check if we already have a clone of this list
                if self.has_clone_of_list(list_to_add):
                    logger.warning(
                        f"Campaign {self.id} already has a clone of list {list_to_add.id}, skipping"
                    )
                    # Return the existing clone
                    return self.lists.get(original_list=list_to_add), False

                # In-progress: clone the list and allocate resources
                campaign_clone = list_to_add.clone(for_campaign=self)
                self.lists.add(campaign_clone)

                # Distribute budget credits to the new gang
                self._distribute_budget_to_list(campaign_clone)

                # Allocate default resources to the new list
                for resource_type in self.resource_types.all():
                    CampaignListResource.objects.get_or_create(
                        campaign=self,
                        resource_type=resource_type,
                        list=campaign_clone,
                        defaults={
                            "amount": resource_type.default_amount,
                            "owner": self.owner,  # Campaign owner owns the resource tracking
                        },
                    )

                return campaign_clone, True
        else:
            # Post-campaign: cannot add lists
            raise ValueError("Cannot add lists to a completed campaign")


class CampaignAction(AppBase):
    """An action taken during a campaign with optional dice rolls"""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="actions",
        help_text="The campaign this action belongs to",
        db_index=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="campaign_actions",
        help_text="The user who performed this action",
        null=True,
        blank=True,
        db_index=True,
    )
    list = models.ForeignKey(
        "List",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaign_actions",
        help_text="The list this action is related to",
        db_index=True,
    )
    battle = models.ForeignKey(
        "Battle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actions",
        help_text="The battle this action is related to",
        db_index=True,
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
        default=pylist, blank=True, help_text="Results of each die rolled"
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
    property_schema = models.JSONField(
        default=pylist,
        blank=True,
        help_text="Schema defining available properties for assets of this type. "
        "Format: [{'key': 'boon', 'label': 'Boon'}, ...]",
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
    properties = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom properties for this asset (e.g., boons, income, location)",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Campaign Asset"
        verbose_name_plural = "Campaign Assets"
        ordering = ["asset_type", "name"]

    def __str__(self):
        return f"{self.name} ({self.asset_type.name_singular})"

    @property
    def properties_with_labels(self):
        """Return properties as a list of (label, value) tuples.

        Looks up the label from the asset_type's property_schema.
        Falls back to the key if no label is defined.
        """
        if not self.properties:
            return []

        # Build a key -> label lookup from the schema
        schema_lookup = {}
        for prop in self.asset_type.property_schema or []:
            key = prop.get("key", "")
            label = prop.get("label", key)
            if key:
                schema_lookup[key] = label

        # Return properties with labels
        result = []
        for key, value in self.properties.items():
            if value:  # Only include non-empty values
                label = schema_lookup.get(key, key)
                result.append((label, value))
        return result

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
                list=new_holder,
                description=description,
                dice_count=0,
                owner=user,
            )


class CampaignResourceType(AppBase):
    """Type of resource tracked in a campaign (e.g., Meat, Ammo, Credits)"""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="resource_types",
        help_text="The campaign this resource type belongs to",
    )
    name = models.CharField(
        max_length=100,
        help_text="Name of the resource (e.g., 'Meat', 'Credits')",
        validators=[validators.MinLengthValidator(1)],
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this resource type",
    )
    default_amount = models.PositiveIntegerField(
        default=0,
        help_text="Default amount allocated to each list when campaign starts",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Campaign Resource Type"
        verbose_name_plural = "Campaign Resource Types"
        unique_together = [("campaign", "name")]
        ordering = ["name"]

    def __str__(self):
        return f"{self.campaign.name} - {self.name}"


class CampaignListResource(AppBase):
    """Tracks the amount of a resource that a list has in a campaign"""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="list_resources",
        help_text="The campaign this resource belongs to",
    )
    resource_type = models.ForeignKey(
        CampaignResourceType,
        on_delete=models.CASCADE,
        related_name="list_resources",
        help_text="The type of resource",
    )
    list = models.ForeignKey(
        "List",
        on_delete=models.CASCADE,
        related_name="campaign_resources",
        help_text="The list that has this resource",
    )
    amount = models.PositiveIntegerField(
        default=0,
        help_text="Current amount of this resource",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Campaign List Resource"
        verbose_name_plural = "Campaign List Resources"
        unique_together = [("campaign", "resource_type", "list")]
        ordering = ["resource_type__name", "list__name"]

    def __str__(self):
        return f"{self.list.name} - {self.resource_type.name}: {self.amount}"

    def modify_amount(self, modification, user):
        """Modify the resource amount and log the action

        Args:
            modification: Integer amount to add (positive) or subtract (negative)
            user: The User performing the modification

        Raises:
            ValueError: If modification would result in negative amount
        """
        if not user:
            raise ValueError("User is required for resource modifications")

        new_amount = self.amount + modification
        if new_amount < 0:
            raise ValueError(
                f"Cannot reduce {self.resource_type.name} below zero. Current: {self.amount}, Attempted change: {modification}"
            )

        self.amount = new_amount
        self.save_with_user(user=user)

        # Create action log entry
        if modification > 0:
            action = f"gained {modification}"
        else:
            action = f"lost {abs(modification)}"

        description = f"{self.resource_type.name} Update: {self.list.name} {action} {self.resource_type.name} (new total: {new_amount})"

        CampaignAction.objects.create(
            campaign=self.campaign,
            user=user,
            list=self.list,
            description=description,
            dice_count=0,
            owner=user,
        )
