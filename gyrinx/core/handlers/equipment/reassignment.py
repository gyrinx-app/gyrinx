"""
Business logic handlers for equipment reassignment operations.

These handlers extract the core business logic from views, making them
directly testable without HTTP machinery. All handlers are transactional
and raise ValidationError on failure.
"""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.tracker import track


@dataclass
class EquipmentReassignmentResult:
    """Result of a successful equipment reassignment."""

    assignment: ListFighterEquipmentAssignment
    equipment_cost: int
    from_fighter: ListFighter
    to_fighter: ListFighter
    description: str
    list_action: ListAction
    campaign_action: Optional[CampaignAction]


@transaction.atomic
def handle_equipment_reassignment(
    *,
    user,
    lst: List,
    from_fighter: ListFighter,
    to_fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
) -> EquipmentReassignmentResult:
    """
    Handle the reassignment of equipment from one fighter to another.

    This handler performs the following operations atomically:
    1. Calculates equipment cost BEFORE reassignment
    2. Performs the reassignment (updates and saves assignment)
    3. Calculates equipment cost AFTER reassignment
    4. Calculates deltas based on source/target stash status
    5. Creates CampaignAction if in campaign mode (informational only, no credits)
    6. Creates ListAction to track the reassignment
    7. Tracks if equipment cost changed during reassignment

    Args:
        user: The user performing the reassignment
        lst: The list containing both fighters
        from_fighter: The fighter currently holding the equipment (assignment.list_fighter should equal this)
        to_fighter: The fighter receiving the equipment
        assignment: The equipment assignment (must still be assigned to from_fighter)

    Returns:
        EquipmentReassignmentResult with assignment, cost, description, and actions

    Note:
        Equipment reassignment does not cost credits - credits_delta is always 0.
        However, rating and stash may change depending on fighter types.
    """
    # Calculate cost BEFORE reassignment
    # Note: We calculate the equipment cost both before and after reassignment because
    # the cost may depend on the assigned fighter. This allows us to track if the cost
    # changes as a result of reassignment. If cost_int() is expensive and the cost rarely
    # changes, consider optimizing, but both calculations are required for correctness.
    cost_before = assignment.cost_int()

    # Perform the reassignment
    assignment.list_fighter = to_fighter
    assignment.save_with_user(user=user)

    # Calculate cost AFTER reassignment
    cost_after = assignment.cost_int()

    # Use the cost after reassignment for deltas
    equipment_cost = cost_after
    equipment_name = assignment.content_equipment.name

    # Determine deltas based on source and target fighter types
    from_is_stash = from_fighter.is_stash
    to_is_stash = to_fighter.is_stash

    if from_is_stash and not to_is_stash:
        # Stash → Regular: Move from stash to rating
        rating_delta = equipment_cost
        stash_delta = -equipment_cost
    elif not from_is_stash and to_is_stash:
        # Regular → Stash: Move from rating to stash
        rating_delta = -equipment_cost
        stash_delta = equipment_cost
    else:
        # Regular → Regular or Stash → Stash: No change
        rating_delta = 0
        stash_delta = 0

    # Build ListAction args (credits never change for reassignment)
    la_args = dict(
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=0,  # Reassignment is free
        rating_before=lst.rating_current,
        stash_before=lst.stash_current,
        credits_before=lst.credits_current,
    )

    # Build user-friendly description based on fighter types
    if from_is_stash and to_is_stash:
        # Shouldn't happen, but handle it
        description = f"Reassigned {equipment_name} to stash ({equipment_cost}¢)"
    elif from_is_stash:
        # From stash to regular fighter
        description = f"Equipped {to_fighter.name} with {equipment_name} from stash ({equipment_cost}¢)"
    elif to_is_stash:
        # From regular fighter to stash
        description = f"Moved {equipment_name} from {from_fighter.name} to stash ({equipment_cost}¢)"
    else:
        # Between regular fighters
        description = f"Reassigned {equipment_name} from {from_fighter.name} to {to_fighter.name} ({equipment_cost}¢)"

    # Create CampaignAction if in campaign mode (informational only, no credits spent)
    campaign_action = None
    if lst.is_campaign_mode:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=description,
            outcome=f"Credits remaining: {lst.credits_current}¢",
        )

    # Create ListAction to track the reassignment
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=description,
        list_fighter=to_fighter,  # New owner
        list_fighter_equipment_assignment=assignment,
        **la_args,
    )

    # Track if equipment cost changed during reassignment
    if cost_before != cost_after:
        cost_differential = cost_after - cost_before
        track(
            "equipment_cost_changed_on_reassignment",
            from_fighter_id=str(from_fighter.id),
            to_fighter_id=str(to_fighter.id),
            from_content_fighter=from_fighter.content_fighter.type,
            to_content_fighter=to_fighter.content_fighter.type,
            equipment_name=equipment_name,
            cost_before=cost_before,
            cost_after=cost_after,
            cost_differential=cost_differential,
            assignment_id=str(assignment.id),
            list_id=str(lst.id),
        )

    return EquipmentReassignmentResult(
        assignment=assignment,
        equipment_cost=equipment_cost,
        from_fighter=from_fighter,
        to_fighter=to_fighter,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )
