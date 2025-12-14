"""Handlers for fighter hire and clone operations."""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.content.models import ContentFighter
from gyrinx.core.cost.propagation import Delta, propagate_from_fighter
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import List, ListFighter
from gyrinx.models import FighterCategoryChoices
from gyrinx.tracing import traced


@dataclass
class FighterHireResult:
    """Result of hiring a fighter."""

    fighter: ListFighter
    fighter_cost: int
    description: str
    list_action: ListAction
    campaign_action: Optional[CampaignAction]


@dataclass
class FighterCloneParams:
    """Parameters for cloning a fighter."""

    name: str
    content_fighter: ContentFighter
    target_list: List
    category_override: Optional[FighterCategoryChoices] = None


@dataclass
class FighterCloneResult:
    """Result of cloning a fighter."""

    fighter: ListFighter
    source_fighter: ListFighter
    fighter_cost: int
    description: str
    list_action: ListAction
    campaign_action: Optional[CampaignAction]


@traced("handle_fighter_hire")
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

    # Initialize rating_current before saving
    propagate_from_fighter(
        fighter,
        Delta(delta=fighter_cost, list=lst),
    )

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


@traced("handle_fighter_clone")
@transaction.atomic
def handle_fighter_clone(
    *,
    user,
    source_fighter: ListFighter,
    clone_params: FighterCloneParams,
) -> FighterCloneResult:
    """
    Handle cloning a fighter to a list.

    Performs the clone operation, creates ListAction on the target list,
    and handles credits in campaign mode. The source list is unaffected.

    Args:
        user: The user performing the clone
        source_fighter: The original fighter being cloned
        clone_params: Parameters for the clone operation (name, target list, etc.)

    Returns:
        FighterCloneResult with created objects

    Raises:
        ValidationError: If insufficient credits in campaign mode
    """
    target_list = clone_params.target_list

    # Capture before values BEFORE clone (clone will create and save the fighter)
    rating_before = target_list.rating_current
    stash_before = target_list.stash_current
    credits_before = target_list.credits_current

    # Clone the fighter with the provided parameters
    # Note: clone() creates and saves the fighter internally
    new_fighter = source_fighter.clone(
        name=clone_params.name,
        content_fighter=clone_params.content_fighter,
        list=clone_params.target_list,
        category_override=clone_params.category_override,
    )

    # Calculate cost after creation
    fighter_cost = new_fighter.cost_int()

    # Initialize rating_current and re-save
    propagate_from_fighter(
        new_fighter,
        Delta(delta=fighter_cost, list=target_list),
    )

    # Determine deltas based on fighter type
    rating_delta = fighter_cost if not new_fighter.is_stash else 0
    stash_delta = fighter_cost if new_fighter.is_stash else 0
    credits_delta = -fighter_cost if target_list.is_campaign_mode else 0

    # Spend credits in campaign mode (raises ValidationError if insufficient)
    # If this fails, @transaction.atomic rolls back the clone
    if target_list.is_campaign_mode:
        target_list.spend_credits(
            fighter_cost, description=f"Cloning {source_fighter.name}"
        )

    # Create CampaignAction if in campaign mode
    campaign_action = None
    if target_list.is_campaign_mode:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=target_list.campaign,
            list=target_list,
            description=f"Cloned {new_fighter.name} from {source_fighter.name} ({fighter_cost}¢)",
            outcome=f"Credits remaining: {target_list.credits_current}¢",
        )

    # Create ListAction on the target list
    description = (
        f"Cloned {new_fighter.name} from {source_fighter.name} ({fighter_cost}¢)"
    )
    list_action = target_list.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=new_fighter.id,
        description=description,
        list_fighter=new_fighter,
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    return FighterCloneResult(
        fighter=new_fighter,
        source_fighter=source_fighter,
        fighter_cost=fighter_cost,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )
