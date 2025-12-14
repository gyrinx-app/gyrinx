"""
Business logic handlers for vehicle purchase operations.

These handlers extract the core business logic from views, making them
directly testable without HTTP machinery. All handlers are transactional
and raise ValidationError on failure.
"""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
)
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


@dataclass
class VehiclePurchaseResult:
    """Result of a successful vehicle purchase."""

    vehicle_assignment: ListFighterEquipmentAssignment
    crew_fighter: ListFighter
    vehicle_cost: int
    crew_cost: int
    total_cost: int
    is_stash: bool
    description: str
    crew_list_action: Optional[ListAction]  # Only when not stash
    vehicle_list_action: ListAction
    campaign_action: Optional[CampaignAction]


@traced("handle_vehicle_purchase")
@transaction.atomic
def handle_vehicle_purchase(
    *,
    user,
    lst: List,
    vehicle_equipment: ContentEquipment,
    vehicle_fighter: ContentFighter,
    crew_fighter: Optional[ContentFighter],
    crew_name: Optional[str],
    is_stash: bool,
) -> VehiclePurchaseResult:
    """
    Handle the purchase of a vehicle with crew or to stash.

    This handler performs the following operations atomically:
    1. Calculates total cost (vehicle + crew if applicable)
    2. Spends credits if in campaign mode
    3. Creates or retrieves crew member (new fighter or stash)
    4. Creates equipment assignment for the vehicle
    5. Creates CampaignAction if in campaign mode
    6. Creates ListAction(s) to track the purchase

    Args:
        user: The user making the purchase
        lst: The list to add the vehicle to
        vehicle_equipment: The vehicle equipment being purchased
        vehicle_fighter: The ContentFighter template for the vehicle
        crew_fighter: The ContentFighter template for crew (None if is_stash=True)
        crew_name: Name for the crew member (None if is_stash=True)
        is_stash: True if adding to stash, False if creating new crew

    Returns:
        VehiclePurchaseResult with assignment, costs, fighter, and actions

    Raises:
        ValidationError: If the purchase cannot be completed (e.g., insufficient credits)
    """
    # Calculate total cost
    vehicle_cost = vehicle_fighter.cost_for_house(lst.content_house)
    crew_cost = crew_fighter.cost_for_house(lst.content_house) if crew_fighter else 0
    total_cost = vehicle_cost + crew_cost

    # Build these beforehand so we get the credit values right
    la_args = dict(
        rating_before=lst.rating_current,
        stash_before=lst.stash_current,
        credits_before=lst.credits_current,
    )

    # Spend credits in campaign mode
    if lst.is_campaign_mode:
        lst.spend_credits(
            total_cost,
            description=f"Adding vehicle '{vehicle_equipment.name}'",
        )

    # Create the crew member
    if not is_stash:
        crew = ListFighter.objects.create(
            list=lst,
            owner=lst.owner,
            name=crew_name,
            content_fighter=crew_fighter,
        )

        # Initialize rating_current to match cost_int()
        propagate_from_fighter(crew, Delta(delta=crew_cost, list=lst))
    else:
        # We are adding to stash, so make sure there's stash fighter
        crew = lst.ensure_stash()

    # Create the equipment assignment - this will trigger automatic vehicle creation
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=crew,
        content_equipment=vehicle_equipment,
    )

    # Propagate to initialize assignment.rating_current and update crew.rating_current
    propagate_from_assignment(assignment, Delta(delta=vehicle_cost, list=lst))

    # Create campaign action for vehicle purchase in campaign mode
    campaign_action = None
    if lst.is_campaign_mode:
        if is_stash:
            description = f"Purchased {vehicle_equipment.name} ({total_cost}¢)"
        else:
            description = f"Purchased {vehicle_equipment.name} and crew {crew.name} ({total_cost}¢)"

        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=description,
            outcome=f"Credits remaining: {lst.credits_current}¢",
        )

    # Create ListAction to track the vehicle purchase
    if is_stash:
        action_description = f"Purchased {vehicle_equipment.name} ({total_cost}¢)"
    else:
        action_description = (
            f"Purchased {vehicle_equipment.name} and crew {crew.name} ({total_cost}¢)"
        )

    # Useful to have separate actions for crew and vehicle for easier tracking of what happened
    crew_list_action = None
    if not is_stash:
        crew_list_action = lst.create_action(
            user=user,
            action_type=ListActionType.ADD_FIGHTER,
            description=action_description,
            list_fighter=crew,
            rating_delta=crew_cost,
            stash_delta=0,
            credits_delta=-crew_cost if lst.is_campaign_mode else 0,
            **la_args,
        )

    vehicle_list_action = lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        description=action_description,
        list_fighter=None if is_stash else crew,
        list_fighter_equipment_assignment=assignment,
        rating_delta=vehicle_cost if not is_stash else 0,
        stash_delta=vehicle_cost if is_stash else 0,
        credits_delta=-vehicle_cost if lst.is_campaign_mode else 0,
        **la_args,
    )

    return VehiclePurchaseResult(
        vehicle_assignment=assignment,
        crew_fighter=crew,
        vehicle_cost=vehicle_cost,
        crew_cost=crew_cost,
        total_cost=total_cost,
        is_stash=is_stash,
        description=action_description,
        crew_list_action=crew_list_action,
        vehicle_list_action=vehicle_list_action,
        campaign_action=campaign_action,
    )
