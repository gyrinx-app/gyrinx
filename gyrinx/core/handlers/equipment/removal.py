"""
Business logic handlers for equipment removal operations.

These handlers extract the core business logic from views, making them
directly testable without HTTP machinery. All handlers are transactional
and raise ValidationError on failure.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from django.db import transaction

from gyrinx.content.models import (
    ContentEquipmentUpgrade,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    VirtualWeaponProfile,
)
from gyrinx.core.cost.propagation import (
    Delta,
    propagate_from_assignment,
    propagate_from_fighter,
)
from gyrinx.core.handlers.refund import calculate_refund_credits
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.tracing import traced


@dataclass
class EquipmentRemovalResult:
    """Result of removing equipment from a fighter."""

    assignment_id: UUID
    equipment_name: str
    equipment_cost: int
    refund_applied: bool
    description: str
    list_action: Optional[ListAction]


@dataclass
class EquipmentComponentRemovalResult:
    """Result of removing upgrade/profile/accessory from equipment."""

    assignment: ListFighterEquipmentAssignment
    component_type: str  # "upgrade" | "profile" | "accessory"
    component_name: str
    component_cost: int
    refund_applied: bool
    description: str
    list_action: Optional[ListAction]


@traced("handle_equipment_removal")
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
    5. Creates ListAction to track the removal

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
    credits_delta, refund_applied = calculate_refund_credits(
        lst=lst,
        cost=equipment_cost,
        request_refund=request_refund,
    )

    # Propagate rating changes to fighter (assignment will be deleted, no need to update it)
    # Use the appropriate delta based on fighter type
    fighter_delta = stash_delta if is_stash else rating_delta
    propagate_from_fighter(fighter, Delta(delta=fighter_delta, list=lst))

    # Delete the assignment
    assignment.delete()

    # Build description
    description = f"Removed {equipment_name} from {fighter.name} ({equipment_cost}¢)"
    if refund_applied:
        description += f" - refund applied (+{equipment_cost}¢)"

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
    )


@traced("handle_equipment_component_removal")
@transaction.atomic
def handle_equipment_component_removal(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
    component_type: str,
    component: ContentEquipmentUpgrade | ContentWeaponProfile | ContentWeaponAccessory,
    request_refund: bool,
) -> EquipmentComponentRemovalResult:
    """
    Handle removal of upgrade/profile/accessory from equipment.

    This handler provides a single implementation for removing any type of
    equipment component, reducing code duplication across views.

    This handler performs the following operations atomically:
    1. Captures before values for ListAction
    2. Calculates component cost based on type
    3. Validates and calculates refund (only in campaign mode)
    4. Removes the component from the assignment
    5. Creates ListAction to track the removal

    Args:
        user: User performing removal
        lst: List containing fighter
        fighter: Fighter owning assignment
        assignment: Assignment to update
        component_type: Type of component ("upgrade", "profile", "accessory")
        component: Component object to remove
        request_refund: Whether user requested refund (only applied in campaign mode)

    Returns:
        EquipmentComponentRemovalResult with removal details

    Raises:
        ValueError: If component_type is not recognized
    """
    # Capture BEFORE values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate cost and remove component based on type
    if component_type == "upgrade":
        component_cost = assignment._upgrade_cost_with_override(component)
        component_name = component.name
    elif component_type == "profile":
        virtual_profile = VirtualWeaponProfile(profile=component)
        component_cost = assignment.profile_cost_int(virtual_profile)
        component_name = component.name
    elif component_type == "accessory":
        component_cost = assignment.accessory_cost_int(component)
        component_name = component.name
    else:
        raise ValueError(f"Unknown component_type: {component_type}")

    # Calculate deltas based on fighter type
    is_stash = fighter.is_stash
    rating_delta = -component_cost if not is_stash else 0
    stash_delta = -component_cost if is_stash else 0

    # Validate and calculate refund
    credits_delta, refund_applied = calculate_refund_credits(
        lst=lst,
        cost=component_cost,
        request_refund=request_refund,
    )

    # Remove the component based on type
    if component_type == "upgrade":
        assignment.upgrades_field.remove(component)
    elif component_type == "profile":
        assignment.weapon_profiles_field.remove(component)
    elif component_type == "accessory":
        assignment.weapon_accessories_field.remove(component)

    # Build description
    description = f"Removed {component_type} {component_name} from {assignment.content_equipment.name} on {fighter.name} ({component_cost}¢)"
    if refund_applied:
        description += f" - refund applied (+{component_cost}¢)"

    propagate_from_assignment(assignment, Delta(delta=rating_delta, list=lst))

    # Create ListAction
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        list_fighter=fighter,
        list_fighter_equipment_assignment=assignment,
        description=description,
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
        update_credits=True,
    )

    return EquipmentComponentRemovalResult(
        assignment=assignment,
        component_type=component_type,
        component_name=component_name,
        component_cost=component_cost,
        refund_applied=refund_applied,
        description=description,
        list_action=list_action,
    )
