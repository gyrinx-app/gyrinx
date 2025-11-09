"""Handlers for fighter operations (hiring, etc.)."""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import List, ListFighter


@dataclass
class FighterHireResult:
    """Result of hiring a fighter."""

    fighter: ListFighter
    fighter_cost: int
    description: str
    list_action: ListAction
    campaign_action: Optional[CampaignAction]


@transaction.atomic
def handle_fighter_hire(
    *,
    user,
    lst: List,
    fighter: ListFighter,
) -> FighterHireResult:
    """
    Handle hiring a fighter to a list.

    Creates the fighter, spends credits (if in campaign mode), and creates
    appropriate ListAction and CampaignAction records.

    Args:
        user: The user performing the hire
        lst: The list to add the fighter to
        fighter: The fighter instance (not yet saved)

    Returns:
        FighterHireResult with created objects

    Raises:
        ValidationError: If insufficient credits in campaign mode
    """
    # Calculate cost before saving
    fighter_cost = fighter.cost_int()

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Determine deltas based on fighter type
    rating_delta = fighter_cost if not fighter.is_stash else 0
    stash_delta = fighter_cost if fighter.is_stash else 0
    credits_delta = -fighter_cost if lst.is_campaign_mode else 0

    # Spend credits in campaign mode (raises ValidationError if insufficient)
    if lst.is_campaign_mode:
        lst.spend_credits(fighter_cost, description=f"Hiring {fighter.name}")

    # Save the fighter
    fighter.save()

    # Create CampaignAction if in campaign mode
    campaign_action = None
    if lst.is_campaign_mode:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"Hired {fighter.name} ({fighter_cost}¢)",
            outcome=f"Credits remaining: {lst.credits_current}¢",
        )

    # Create ListAction
    description = f"Hired {fighter.name} ({fighter_cost}¢)"
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=description,
        list_fighter=fighter,
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    return FighterHireResult(
        fighter=fighter,
        fighter_cost=fighter_cost,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )
