"""Handler for equipment cost override operations."""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)


@dataclass
class EquipmentCostOverrideResult:
    """Result of changing equipment total_cost_override."""

    assignment: ListFighterEquipmentAssignment
    old_total_cost: int
    new_total_cost: int
    cost_delta: int
    description: str
    list_action: ListAction


def _calculate_cost_without_override(
    assignment: ListFighterEquipmentAssignment,
) -> int:
    """Calculate the assignment's cost without any total_cost_override."""
    return (
        assignment.base_cost_int_cached
        + assignment.weapon_profiles_cost_int_cached
        + assignment.weapon_accessories_cost_int_cached
        + assignment.upgrade_cost_int_cached
    )


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
    calculated_cost = _calculate_cost_without_override(assignment)

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


@transaction.atomic
def handle_equipment_cost_override(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
    new_total_cost_override: Optional[int],
) -> Optional[EquipmentCostOverrideResult]:
    """
    Handle equipment total_cost_override change with ListAction tracking.

    Creates an UPDATE_EQUIPMENT ListAction to track the cost delta from the
    override change. The delta goes to rating_delta or stash_delta depending
    on whether the fighter is stash-linked.

    Args:
        user: The user making the change
        lst: The list the fighter belongs to
        fighter: The fighter whose equipment is being modified
        assignment: The equipment assignment to update
        new_total_cost_override: New override value (None to clear)

    Returns:
        EquipmentCostOverrideResult with assignment, costs, and action,
        or None if no change occurred
    """
    old_override = assignment.total_cost_override

    # Check if anything is actually changing
    if old_override == new_total_cost_override:
        return None

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate delta
    old_total_cost, new_total_cost, cost_delta = _calculate_cost_delta(
        assignment, old_override, new_total_cost_override
    )

    # Determine if this goes to stash or rating
    is_stash = fighter.is_stash

    # Generate description
    description = _generate_description(
        assignment, fighter, old_override, new_total_cost_override, cost_delta
    )

    # Apply the change
    assignment.total_cost_override = new_total_cost_override
    assignment.save()

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
