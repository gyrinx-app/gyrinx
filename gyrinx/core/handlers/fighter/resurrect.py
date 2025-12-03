"""Handler for fighter resurrection operations in campaign mode."""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListFighter


@dataclass
class FighterResurrectResult:
    """Result of resurrecting a dead fighter."""

    fighter: ListFighter
    restored_cost: int
    list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]
    description: str


@transaction.atomic
def handle_fighter_resurrect(
    *,
    user,
    fighter: ListFighter,
) -> FighterResurrectResult:
    """
    Resurrect a dead fighter, restoring their cost to the list rating.

    This handler performs the following operations atomically:
    1. Captures before values from the list
    2. Calculates the cost that will be restored
    3. Sets injury_state to ACTIVE
    4. Clears cost_override (restores original cost)
    5. Saves the fighter
    6. Creates UPDATE_FIGHTER ListAction to track rating increase
    7. Creates CampaignAction if in campaign

    Note: Equipment is NOT restored - it remains in the stash and must be
    manually re-equipped by the user.

    Args:
        user: The user performing the resurrection
        fighter: The dead fighter to resurrect (must have injury_state=DEAD)

    Returns:
        FighterResurrectResult with fighter, restored cost, and actions

    Raises:
        ValueError: If fighter is not dead, is stash, or list not in campaign mode
    """
    lst = fighter.list

    # Validate preconditions
    if not lst.is_campaign_mode:
        raise ValueError("Fighters can only be resurrected in campaign mode")

    if fighter.is_stash:
        raise ValueError("Cannot resurrect the stash")

    if fighter.injury_state != ListFighter.DEAD:
        raise ValueError("Only dead fighters can be resurrected")

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate what the cost WILL BE after we clear cost_override
    # Dead fighters have cost_override=0, so we need the original base cost
    restored_cost = fighter._base_cost_before_override()

    # Apply mutations
    fighter.injury_state = ListFighter.ACTIVE
    fighter.cost_override = None  # Restores original cost
    fighter.save()

    # Build description
    description = f"{fighter.name} resurrected (rating +{restored_cost}¢)"

    # Create UPDATE_FIGHTER ListAction
    # The fighter's cost goes from 0 to restored_cost
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=description,
        list_fighter=fighter,
        rating_delta=restored_cost,
        stash_delta=0,
        credits_delta=0,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    # Create CampaignAction if this list is part of a campaign
    campaign_action = None
    if lst.campaign:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"Resurrection: {fighter.name} is no longer dead",
            outcome=f"{fighter.name} has been returned to the active roster.",
        )

    return FighterResurrectResult(
        fighter=fighter,
        restored_cost=restored_cost,
        list_action=list_action,
        campaign_action=campaign_action,
        description=description,
    )
