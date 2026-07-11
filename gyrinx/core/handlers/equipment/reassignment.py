"""
Business logic handlers for equipment reassignment operations.

These handlers extract the core business logic from views, making them
directly testable without HTTP machinery. All handlers are transactional
and raise ValidationError on failure.
"""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.cost.propagation import (
    Delta,
    propagate_from_assignment,
    propagate_from_fighter,
)
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.tracing import traced
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


@traced("handle_equipment_reassignment")
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
    # Capture BEFORE values for the ListAction ahead of any propagation —
    # propagation writes the list-level cache, so reading these later would
    # capture post-move values and corrupt the action's baseline.
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate cost BEFORE reassignment. The cost can depend on the holder
    # (equipment-list pricing), so it must be recomputed after the move too.
    cost_before = assignment.cost_int()

    # Propagate to from_fighter BEFORE reassignment (decrease their rating)
    propagate_from_fighter(from_fighter, Delta(delta=-cost_before, list=lst))

    # Perform the reassignment
    assignment.list_fighter = to_fighter
    assignment.save_with_user(user=user)

    # Calculate cost AFTER reassignment on a FRESH instance: cost_int() reads
    # per-instance cached_property component costs that populated during the
    # cost_before call and never invalidate, so re-calling it on the same
    # object would always return cost_before and silently mask re-pricing
    # (the #1826-class drift this handler used to produce).
    #
    # The refetch MUST use with_related_data(): its accessory prefetch goes
    # through all_content(), like the instances views hand this handler and
    # like the canonical recompute path. A plain fetch resolves accessories
    # through the pack-excluding default manager, so pack-scoped accessories
    # would vanish from cost_after and book a phantom repricing.
    refreshed = ListFighterEquipmentAssignment.objects.with_related_data().get(
        pk=assignment.pk
    )
    cost_after = refreshed.cost_int()

    # The assignment's own cache still holds the old-context value; shift it
    # by the re-pricing difference. This walks assignment → (new) fighter, so
    # afterwards the to_fighter needs only the cost_before base.
    to_fighter_fresh = refreshed.list_fighter
    propagate_from_assignment(
        refreshed, Delta(delta=cost_after - cost_before, list=lst)
    )
    propagate_from_fighter(to_fighter_fresh, Delta(delta=cost_before, list=lst))

    # Use the cost after reassignment for deltas
    equipment_cost = cost_after
    equipment_name = assignment.content_equipment.name

    # Determine deltas based on source and target fighter types. The value
    # LEAVING the source is cost_before; the value ARRIVING at the target is
    # cost_after — when the move re-prices the gear, the difference is a real
    # book movement and must be recorded, or the caches and the action chain
    # diverge on the next recompute.
    from_is_stash = from_fighter.is_stash
    to_is_stash = to_fighter.is_stash

    if from_is_stash and not to_is_stash:
        # Stash → Regular
        rating_delta = cost_after
        stash_delta = -cost_before
    elif not from_is_stash and to_is_stash:
        # Regular → Stash
        rating_delta = -cost_before
        stash_delta = cost_after
    else:
        # Regular → Regular or Stash → Stash: only the re-pricing moves the book
        rating_delta = (cost_after - cost_before) if not from_is_stash else 0
        stash_delta = (cost_after - cost_before) if from_is_stash else 0

    # Build ListAction args (credits never change for reassignment)
    la_args = dict(
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=0,  # Reassignment is free
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
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
        # Return the refreshed instance: its cached rating reflects the
        # propagation applied above; the original's in-memory state predates it.
        assignment=refreshed,
        equipment_cost=equipment_cost,
        from_fighter=from_fighter,
        to_fighter=to_fighter,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )
