"""Handlers for list credit operations."""

from dataclasses import dataclass
from typing import Literal, Optional

from django.db import transaction

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import List
from gyrinx.tracing import traced


@dataclass
class CreditsModificationResult:
    """Result of modifying credits on a list."""

    lst: List
    operation: str
    amount: int
    credits_before: int
    credits_after: int
    credits_earned_before: int
    credits_earned_after: int
    description: str
    list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]


@traced("handle_credits_modification")
@transaction.atomic
def handle_credits_modification(
    *,
    user,
    lst: List,
    operation: Literal["add", "spend", "reduce"],
    amount: int,
    description: str = "",
) -> CreditsModificationResult:
    """
    Handle modification of credits on a list.

    This handler performs the following operations atomically:
    1. Captures before values for ListAction
    2. Validates the operation (sufficient credits for spend/reduce)
    3. Applies the credit change
    4. Creates ListAction to track the change
    5. Creates CampaignAction if in campaign mode

    Operations:
    - add: Increases credits_current and credits_earned (income)
    - spend: Decreases credits_current only (spending on untracked items)
    - reduce: Decreases both credits_current and credits_earned (correction/penalty)

    Args:
        user: User performing the modification
        lst: List to modify
        operation: Type of operation ("add", "spend", "reduce")
        amount: Amount of credits to add/spend/reduce (must be >= 0)
        description: Optional description of the reason for the change

    Returns:
        CreditsModificationResult with all details

    Raises:
        ValueError: If amount is negative or operation is invalid
        ValueError: If spending/reducing more credits than available
    """
    if amount < 0:
        raise ValueError("Amount must be non-negative")

    if operation not in ("add", "spend", "reduce"):
        raise ValueError(f"Invalid operation: {operation}")

    # Validate sufficient credits for spend/reduce
    if operation == "spend" and amount > lst.credits_current:
        raise ValueError(
            f"Cannot spend more credits than available ({lst.credits_current}¢)"
        )
    if operation == "reduce":
        if amount > lst.credits_current:
            raise ValueError(
                f"Cannot reduce credits below zero (current: {lst.credits_current}¢)"
            )
        if amount > lst.credits_earned:
            raise ValueError(
                f"Cannot reduce all time credits below zero (all time: {lst.credits_earned}¢)"
            )

    # Capture BEFORE values
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current
    credits_earned_before = lst.credits_earned

    # Calculate credits_delta based on operation
    if operation == "add":
        credits_delta = amount
    else:  # spend or reduce
        credits_delta = -amount

    # For "reduce" operation, we need to also decrease credits_earned.
    # The create_action method only increases credits_earned for positive deltas,
    # so we manually decrement it here before calling create_action.
    # create_action will then save this decremented value.
    if operation == "reduce":
        lst.credits_earned -= amount

    # Build action description
    if operation == "add":
        action_desc = f"Added {amount}¢"
    elif operation == "spend":
        action_desc = f"Spent {amount}¢"
    else:  # reduce
        action_desc = f"Reduced {amount}¢"

    if description:
        action_desc += f": {description}"

    # Create ListAction with credits update
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description=action_desc,
        rating_delta=0,
        stash_delta=0,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
        update_credits=True,
    )

    # Calculate after values for result
    lst.refresh_from_db()
    credits_after = lst.credits_current
    credits_earned_after = lst.credits_earned

    # Build outcome description for CampaignAction
    if operation == "add":
        outcome = f"+{amount}¢ (to {credits_after}¢)"
    elif operation == "spend":
        outcome = f"-{amount}¢ (to {credits_after}¢)"
    else:  # reduce
        outcome = f"-{amount}¢ (to {credits_after}¢, all time: {credits_earned_after}¢)"

    # Create CampaignAction if in campaign mode
    campaign_action = None
    if lst.is_campaign_mode and lst.campaign:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=action_desc,
            outcome=outcome,
        )

    return CreditsModificationResult(
        lst=lst,
        operation=operation,
        amount=amount,
        credits_before=credits_before,
        credits_after=credits_after,
        credits_earned_before=credits_earned_before,
        credits_earned_after=credits_earned_after,
        description=action_desc,
        list_action=list_action,
        campaign_action=campaign_action,
    )
