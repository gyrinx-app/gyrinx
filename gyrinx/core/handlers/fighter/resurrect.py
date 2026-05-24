"""Handler for fighter resurrection operations in campaign mode."""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.cost.propagation import Delta, propagate_from_fighter
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListFighter
from gyrinx.tracing import traced


# Injury states a dead fighter may be moved into when leaving DEAD. DEAD itself
# is excluded — resurrection always takes the fighter out of death.
RESURRECT_TARGET_STATES = (
    ListFighter.ACTIVE,
    ListFighter.RECOVERY,
    ListFighter.CONVALESCENCE,
    ListFighter.IN_REPAIR,
)


@dataclass
class FighterResurrectResult:
    """Result of resurrecting a dead fighter."""

    fighter: ListFighter
    restored_cost: int
    target_state: str
    list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]
    description: str


@traced("handle_fighter_resurrect")
@transaction.atomic
def handle_fighter_resurrect(
    *,
    user,
    fighter: ListFighter,
    target_state: str = ListFighter.ACTIVE,
    create_campaign_action: bool = True,
) -> FighterResurrectResult:
    """
    Bring a dead fighter back out of the DEAD state, restoring their cost.

    Killing a fighter sets ``cost_override=0`` alongside ``injury_state=DEAD``.
    This handler is the single place that clears that override when a fighter
    leaves DEAD, so any DEAD → non-DEAD transition must route through here
    rather than saving ``injury_state`` directly (see #1782).

    This handler performs the following operations atomically:
    1. Captures before values from the list
    2. Calculates the cost that will be restored
    3. Sets injury_state to the target state (default ACTIVE)
    4. Clears cost_override (restores original cost)
    5. Saves the fighter
    6. Creates UPDATE_FIGHTER ListAction to track rating increase
    7. Creates CampaignAction if in campaign (unless suppressed)

    Note: Equipment is NOT restored - it remains in the stash and must be
    manually re-equipped by the user.

    Args:
        user: The user performing the resurrection
        fighter: The dead fighter to resurrect (must have injury_state=DEAD)
        target_state: The non-DEAD injury state to move the fighter into.
            Defaults to ACTIVE.
        create_campaign_action: Whether to log a CampaignAction. Callers that
            already log their own action (e.g. removing the last injury) can
            set this to False to avoid a duplicate log line.

    Returns:
        FighterResurrectResult with fighter, restored cost, and actions

    Raises:
        ValueError: If fighter is not dead, is stash, list not in campaign
            mode, or target_state is not a valid non-DEAD state
    """
    lst = fighter.list

    # Validate preconditions
    if not lst.is_campaign_mode:
        raise ValueError("Fighters can only be resurrected in campaign mode")

    if fighter.is_stash:
        raise ValueError("Cannot resurrect the stash")

    if fighter.injury_state != ListFighter.DEAD:
        raise ValueError("Only dead fighters can be resurrected")

    if target_state not in RESURRECT_TARGET_STATES:
        raise ValueError(
            f"Cannot resurrect a fighter into state {target_state!r}; "
            f"must be one of {RESURRECT_TARGET_STATES}"
        )

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate what the cost WILL BE after we clear cost_override
    # Dead fighters have cost_override=0, so we need the original base cost
    restored_cost = fighter._base_cost_before_override()

    # Apply mutations
    fighter.injury_state = target_state
    fighter.cost_override = None  # Restores original cost
    fighter.save(update_fields=["injury_state", "cost_override"])

    # Propagate the cost restoration (0 → restored_cost)
    propagate_from_fighter(fighter, Delta(delta=restored_cost, list=lst))

    # Build description
    if target_state == ListFighter.ACTIVE:
        description = f"{fighter.name} resurrected (rating +{restored_cost}¢)"
    else:
        target_display = dict(ListFighter.INJURY_STATE_CHOICES)[target_state]
        description = (
            f"{fighter.name} is no longer dead, now {target_display} "
            f"(rating +{restored_cost}¢)"
        )

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
    if lst.campaign and create_campaign_action:
        if target_state == ListFighter.ACTIVE:
            outcome = f"{fighter.name} has been returned to the active roster."
        else:
            target_display = dict(ListFighter.INJURY_STATE_CHOICES)[target_state]
            outcome = f"{fighter.name} is no longer dead and is now {target_display}."
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"Resurrection: {fighter.name} is no longer dead",
            outcome=outcome,
        )

    return FighterResurrectResult(
        fighter=fighter,
        restored_cost=restored_cost,
        target_state=target_state,
        list_action=list_action,
        campaign_action=campaign_action,
        description=description,
    )
