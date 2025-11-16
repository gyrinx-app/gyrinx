"""Handlers for campaign operations (starting campaigns, etc.)."""

import logging
from dataclasses import dataclass
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import Campaign, CampaignAction, CampaignListResource
from gyrinx.core.models.list import List

logger = logging.getLogger(__name__)


@dataclass
class ListBudgetDistributionResult:
    """Result of distributing budget to a single list."""

    campaign_list: List
    list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]
    credits_added: int
    reason: str = ""


@dataclass
class CampaignStartResult:
    """Result of starting a campaign."""

    campaign: Campaign
    list_results: list[ListBudgetDistributionResult]
    overall_campaign_action: CampaignAction


@transaction.atomic
def handle_campaign_start(
    *,
    user,
    campaign: Campaign,
) -> CampaignStartResult:
    """
    Handle starting a campaign.

    This owns ALL campaign start logic including:
    - Validating campaign can be started
    - Cloning all LIST_BUILDING lists to CAMPAIGN_MODE
    - Distributing budget credits to each list
    - Creating ListAction for each credit distribution
    - Creating CampaignActions for tracking
    - Creating CampaignListResource entries
    - Updating campaign status to IN_PROGRESS

    Args:
        user: The user starting the campaign
        campaign: The campaign to start

    Returns:
        CampaignStartResult with all created actions and lists

    Raises:
        ValidationError: If campaign cannot be started
    """
    logger.info(f"Starting campaign {campaign.id} by user {user.id}")

    # Validate campaign can be started
    if not campaign.can_start_campaign():
        if campaign.status != Campaign.PRE_CAMPAIGN:
            raise ValidationError(
                f"Campaign cannot be started. Current status: {campaign.get_status_display()}"
            )
        elif not campaign.lists.exists():
            raise ValidationError("Campaign cannot be started without lists.")
        else:
            raise ValidationError("Campaign cannot be started.")

    # Get all LIST_BUILDING lists before clearing
    original_lists: list[List] = list(campaign.lists.filter(status=List.LIST_BUILDING))
    logger.info(
        f"Campaign {campaign.id} has {len(original_lists)} lists to clone for campaign start"
    )
    campaign.lists.clear()

    cloned_lists = []
    list_results = []

    # Clone each list and distribute budget
    for original_list in original_lists:
        # Check if we already have a clone of this list
        existing_clone = List.objects.filter(
            original_list=original_list,
            campaign=campaign,
            status=List.CAMPAIGN_MODE,
        ).first()

        if existing_clone:
            logger.warning(
                f"Campaign {campaign.id} already has a clone of list {original_list.id}, re-adding existing clone"
            )
            # Re-add the existing clone to the campaign
            campaign.lists.add(existing_clone)
            cloned_lists.append(existing_clone)
            # Don't distribute budget to existing clones
            list_results.append(
                ListBudgetDistributionResult(
                    campaign_list=existing_clone,
                    list_action=None,
                    campaign_action=None,
                    credits_added=0,
                )
            )
            continue

        # Clone the list for campaign mode
        campaign_clone = original_list.clone(for_campaign=campaign)

        # Track cloning
        campaign.lists.add(campaign_clone)
        cloned_lists.append(campaign_clone)

        # Distribute budget credits to the cloned list
        budget_result = _distribute_budget_to_list(
            user=user,
            campaign=campaign,
            campaign_list=campaign_clone,
            # NOTE: This computes the cost from scratch; we would prefer to use *_current but can't yet. #1054
            list_cost=original_list.cost_int_cached,
        )
        logger.info(
            f"Distributed {budget_result.credits_added}¢ to list {campaign_clone.id} for campaign {campaign.id} based on list cost of {original_list.cost_int_cached}¢"
        )
        list_results.append(budget_result)

    # Allocate default resources to each list
    for resource_type in campaign.resource_types.all():
        for cloned_list in cloned_lists:
            logger.info(
                f"Allocating default resource {resource_type.id} to list {cloned_list.id} for campaign {campaign.id} of amount {resource_type.default_amount}"
            )
            CampaignListResource.objects.get_or_create(
                campaign=campaign,
                resource_type=resource_type,
                list=cloned_list,
                defaults={
                    "amount": resource_type.default_amount,
                    "owner": campaign.owner,
                },
            )

    # Update campaign status to IN_PROGRESS
    campaign.status = Campaign.IN_PROGRESS
    campaign.save()

    # Create overall campaign action
    overall_campaign_action = CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        description=f"Campaign Started: {campaign.name} is now in progress",
        outcome=f"{len(cloned_lists)} gang(s) joined the campaign",
        owner=user,
    )

    return CampaignStartResult(
        campaign=campaign,
        list_results=list_results,
        overall_campaign_action=overall_campaign_action,
    )


def _distribute_budget_to_list(
    *,
    user,
    campaign: Campaign,
    campaign_list: List,
    list_cost: int,
) -> ListBudgetDistributionResult:
    """
    Distribute campaign starting budget to a list.

    Creates ListAction to track the credit distribution and updates
    the list's credits atomically.

    Args:
        user: The user performing the distribution
        campaign: The campaign providing the budget
        campaign_list: The list receiving the budget

    Returns:
        ListBudgetDistributionResult with created actions and credits added
    """
    if campaign.budget <= 0:
        return ListBudgetDistributionResult(
            campaign_list=campaign_list,
            list_action=None,
            campaign_action=None,
            credits_added=0,
            reason="Campaign budget is zero",
        )

    # Calculate credits to add: max(0, budget - list cost)
    # List cost is the rating + stash (excluding any existing credits)
    credits_to_add = max(0, campaign.budget - list_cost)

    if credits_to_add <= 0:
        return ListBudgetDistributionResult(
            campaign_list=campaign_list,
            list_action=None,
            campaign_action=None,
            credits_added=0,
            reason="List cost exceeds or meets campaign budget",
        )

    description = f"Campaign starting budget: Received {credits_to_add}¢ ({campaign.budget}¢ budget - {list_cost}¢ gang cost)"

    # Update list credits via an action transaction
    list_action = campaign_list.create_action(
        user=user,
        update_credits=True,
        action_type=ListActionType.CAMPAIGN_START,
        subject_app="core",
        subject_type="Campaign",
        subject_id=campaign.id,
        description=description,
        rating_delta=0,
        stash_delta=0,
        credits_delta=credits_to_add,
    )

    # Create CampaignAction for visibility
    campaign_action = CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        list=campaign_list,
        description=description,
        outcome=f"+{credits_to_add}¢ (to {campaign_list.credits_current}¢)",
        owner=user,
    )

    return ListBudgetDistributionResult(
        campaign_list=campaign_list,
        list_action=list_action,
        campaign_action=campaign_action,
        credits_added=credits_to_add,
        reason="Budget distributed successfully",
    )
