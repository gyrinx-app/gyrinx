"""Handler for equipment cost override operations."""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.cost.propagation import Delta, propagate_from_assignment
from gyrinx.core.cost.routing import is_stash_linked as check_is_stash_linked
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.tracing import traced


@dataclass
class EquipmentCostOverrideResult:
    """Result of changing equipment total_cost_override."""

    assignment: ListFighterEquipmentAssignment
    old_total_cost: int
    new_total_cost: int
    cost_delta: int
    description: str
    list_action: ListAction


def _calculate_cost_delta(
    assignment: ListFighterEquipmentAssignment,
    old_override: Optional[int],
    new_override: Optional[int],
) -> tuple[int, int, int]:
    """
    Calculate the cost delta when changing total_cost_override.

    Returns:
        Tuple of (old_total_cost, new_total_cost, delta)
    """
    calculated_cost = assignment.calculated_cost_int()

    # Determine old effective cost
    if old_override is not None:
        old_total_cost = old_override
    else:
        old_total_cost = calculated_cost

    # Determine new effective cost
    if new_override is not None:
        new_total_cost = new_override
    else:
        new_total_cost = calculated_cost

    delta = new_total_cost - old_total_cost
    return old_total_cost, new_total_cost, delta


def _generate_description(
    assignment: ListFighterEquipmentAssignment,
    fighter: ListFighter,
    old_override: Optional[int],
    new_override: Optional[int],
    cost_delta: int,
) -> str:
    """Generate a human-readable description for the cost override change."""
    equipment_name = assignment.content_equipment.name

    if old_override is None and new_override is not None:
        return (
            f"Set cost override for {equipment_name} on {fighter.name} "
            f"to {new_override}\u00a2 ({cost_delta:+}\u00a2)"
        )
    elif old_override is not None and new_override is None:
        return (
            f"Removed cost override of {old_override}\u00a2 for {equipment_name} "
            f"on {fighter.name} ({cost_delta:+}\u00a2)"
        )
    else:
        return (
            f"Changed cost override for {equipment_name} on {fighter.name} "
            f"from {old_override}\u00a2 to {new_override}\u00a2 ({cost_delta:+}\u00a2)"
        )


@traced("handle_equipment_cost_override")
@transaction.atomic
def handle_equipment_cost_override(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
    old_total_cost_override: Optional[int],
    new_total_cost_override: Optional[int],
) -> Optional[EquipmentCostOverrideResult]:
    """
    Handle equipment total_cost_override change with ListAction tracking.

    Creates an UPDATE_EQUIPMENT ListAction to track the cost delta from the
    override change. The delta goes to rating_delta or stash_delta depending
    on whether the fighter is stash-linked.

    The assignment object should already have the new value applied (e.g., by
    Django's ModelForm is_valid()). This handler compares the old value passed
    as a parameter with the new value and saves the assignment.

    Args:
        user: The user making the change
        lst: The list the fighter belongs to
        fighter: The fighter whose equipment is being modified
        assignment: The equipment assignment with new value already applied
        old_total_cost_override: Previous override value (before form modified it)
        new_total_cost_override: New override value (None to clear)

    Returns:
        EquipmentCostOverrideResult with assignment, costs, and action,
        or None if no change occurred
    """
    # Check if anything is actually changing
    if old_total_cost_override == new_total_cost_override:
        return None

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate delta
    old_total_cost, new_total_cost, cost_delta = _calculate_cost_delta(
        assignment, old_total_cost_override, new_total_cost_override
    )

    # Determine if this goes to stash or rating
    # Use check_is_stash_linked to handle child fighters (vehicles/exotic beasts)
    # whose parent equipment is on a stash fighter
    is_stash = check_is_stash_linked(fighter)

    # Generate description
    description = _generate_description(
        assignment,
        fighter,
        old_total_cost_override,
        new_total_cost_override,
        cost_delta,
    )

    # Apply the change
    assignment.total_cost_override = new_total_cost_override
    assignment.save(update_fields=["total_cost_override"])

    # Propagate to maintain intermediate node caches (assignment.rating_current, fighter.rating_current)
    delta = Delta(delta=cost_delta, list=lst)
    propagate_from_assignment(assignment, delta)

    # Create ListAction
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=description,
        list_fighter=fighter,
        list_fighter_equipment_assignment=assignment,
        rating_delta=cost_delta if not is_stash else 0,
        stash_delta=cost_delta if is_stash else 0,
        credits_delta=0,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    return EquipmentCostOverrideResult(
        assignment=assignment,
        old_total_cost=old_total_cost,
        new_total_cost=new_total_cost,
        cost_delta=cost_delta,
        description=description,
        list_action=list_action,
    )
