"""Handlers for fighter and equipment removal operations.

These handlers extract business logic for deletion/removal operations,
making them directly testable without HTTP machinery.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from django.db import transaction

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)


@dataclass
class EquipmentRemovalResult:
    """Result of removing equipment from a fighter."""

    assignment_id: UUID
    equipment_name: str
    equipment_cost: int
    refund_applied: bool
    description: str
    list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]


def _calculate_refund_credits(
    *,
    lst: List,
    cost: int,
    request_refund: bool,
) -> tuple[int, bool]:
    """
    Calculate credits delta based on refund request and campaign mode.

    Refunds are ONLY allowed in campaign mode.

    Args:
        lst: The list
        cost: The item cost being removed
        request_refund: Whether user requested refund

    Returns:
        Tuple of (credits_delta, refund_applied)
    """
    refund_applied = request_refund and lst.is_campaign_mode
    credits_delta = cost if refund_applied else 0
    return credits_delta, refund_applied


@transaction.atomic
def handle_equipment_removal(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
    request_refund: bool,
) -> EquipmentRemovalResult:
    """
    Handle removal of equipment assignment from a fighter.

    This handler performs the following operations atomically:
    1. Captures before values for ListAction
    2. Calculates equipment cost before deletion
    3. Validates and calculates refund (only in campaign mode)
    4. Deletes the equipment assignment
    5. Creates CampaignAction if in campaign mode
    6. Creates ListAction to track the removal

    Args:
        user: User performing removal
        lst: List containing fighter
        fighter: Fighter owning assignment
        assignment: Assignment to remove
        request_refund: Whether user requested refund (only applied in campaign mode)

    Returns:
        EquipmentRemovalResult with removal details
    """
    # Capture BEFORE values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate cost BEFORE deletion
    equipment_cost = assignment.cost_int()
    equipment_name = assignment.content_equipment.name
    assignment_id = assignment.id

    # Calculate deltas based on fighter type
    is_stash = fighter.is_stash
    rating_delta = -equipment_cost if not is_stash else 0
    stash_delta = -equipment_cost if is_stash else 0

    # Validate and calculate refund
    credits_delta, refund_applied = _calculate_refund_credits(
        lst=lst,
        cost=equipment_cost,
        request_refund=request_refund,
    )

    # Delete the assignment
    assignment.delete()

    # Build description
    description = f"Removed {equipment_name} from {fighter.name} ({equipment_cost}¢)"
    if refund_applied:
        description += f" - refund applied (+{equipment_cost}¢)"

    # Create CampaignAction if in campaign mode
    campaign_action = None
    if lst.is_campaign_mode:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=description,
            outcome=f"Credits: {credits_before + credits_delta}¢",
        )

    # Create ListAction
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.REMOVE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment_id,
        list_fighter=fighter,
        description=description,
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
        update_credits=True,
    )

    return EquipmentRemovalResult(
        assignment_id=assignment_id,
        equipment_name=equipment_name,
        equipment_cost=equipment_cost,
        refund_applied=refund_applied,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )
