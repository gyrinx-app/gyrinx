"""
Business logic handlers for equipment sale operations.

These handlers extract the core business logic from views, making them
directly testable without HTTP machinery. All handlers are transactional
and raise ValidationError on failure.
"""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.content.models import (
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.core.cost.propagation import Delta, propagate_from_assignment
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.tracing import traced


@dataclass
class SaleItemDetail:
    """Details for a single item being sold."""

    name: str
    cost: int  # Original equipment cost
    sale_price: int  # Final sale price (after dice roll or manual)
    dice_roll: Optional[int]  # Dice roll result (None if manual price)


@dataclass
class EquipmentSaleResult:
    """Result of a successful equipment sale."""

    total_sale_credits: int  # Credits received from sale
    total_equipment_cost: int  # Original equipment cost removed from stash
    description: str
    list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]


@traced("handle_equipment_sale")
@transaction.atomic
def handle_equipment_sale(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
    sell_assignment: bool,
    profiles_to_remove: list[ContentWeaponProfile],
    accessories_to_remove: list[ContentWeaponAccessory],
    sale_items: list[SaleItemDetail],
    dice_count: int,
    dice_rolls: list[int],
) -> EquipmentSaleResult:
    """
    Handle the sale of equipment from a stash fighter.

    This handler performs the following operations atomically:
    1. Validates fighter is a stash fighter
    2. Captures before values for ListAction
    3. Calculates total equipment cost being removed from stash
    4. Deletes assignment or removes profiles/accessories
    5. Adds sale credits to list
    6. Creates CampaignAction with dice roll info (if in campaign mode)
    7. Creates ListAction to track the sale

    Args:
        user: The user performing the sale
        lst: The list the fighter belongs to
        fighter: The stash fighter selling the equipment
        assignment: The equipment assignment being sold from
        sell_assignment: True if selling entire assignment, False if selling components
        profiles_to_remove: Profiles to remove (empty if sell_assignment=True)
        accessories_to_remove: Accessories to remove (empty if sell_assignment=True)
        sale_items: List of SaleItemDetail with name, cost, sale_price for each item
        dice_count: Number of dice rolled
        dice_rolls: List of dice roll results

    Returns:
        EquipmentSaleResult with total credits, description, and actions

    Raises:
        ValidationError: If fighter is not a stash fighter

    Note:
        This handler expects pre-calculated sale prices. The view handles dice
        rolling and price calculation before calling this handler.
    """
    from django.core.exceptions import ValidationError

    # Validate fighter is a stash fighter
    if not fighter.is_stash:
        raise ValidationError("Equipment can only be sold from stash fighters")

    # Calculate totals from typed sale items
    total_equipment_cost = sum(item.cost for item in sale_items)
    total_sale_credits = sum(item.sale_price for item in sale_items)

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate deltas
    # - stash_delta: negative (equipment removed from stash)
    # - credits_delta: positive (sale proceeds added)
    # - rating_delta: 0 (selling is from stash only)
    stash_delta = -total_equipment_cost
    credits_delta = total_sale_credits
    rating_delta = 0

    # Store assignment ID before potential deletion
    assignment_id = assignment.id

    # Delete assignment or remove individual components
    if sell_assignment:
        assignment.delete()
    else:
        # Remove individual profiles
        for profile in profiles_to_remove:
            assignment.weapon_profiles_field.remove(profile)
        # Remove individual accessories
        for accessory in accessories_to_remove:
            assignment.weapon_accessories_field.remove(accessory)

    # Build description from sale items
    description_parts = []
    for item in sale_items:
        if item.dice_roll is not None:
            description_parts.append(
                f"{item.name} ({item.cost}¢ - {item.dice_roll}×10 = {item.sale_price}¢)"
            )
        else:
            description_parts.append(f"{item.name} ({item.sale_price}¢)")

    description = f"Sold equipment from stash: {', '.join(description_parts)}"

    # Create CampaignAction if in campaign mode
    campaign_action = None
    if lst.is_campaign_mode:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=description,
            outcome=f"+{total_sale_credits}¢ (to {lst.credits_current + credits_delta}¢)",
            dice_count=dice_count,
            dice_results=dice_rolls,
            dice_total=sum(dice_rolls) if dice_rolls else 0,
        )

    propagate_from_assignment(assignment, Delta(delta=stash_delta, list=lst))

    # Create ListAction with update_credits=True to apply the credits delta
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.REMOVE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment_id,
        description=description,
        list_fighter=fighter,
        list_fighter_equipment_assignment=None,  # Assignment may be deleted
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
        update_credits=True,  # Apply credits_delta to list
    )

    return EquipmentSaleResult(
        total_sale_credits=total_sale_credits,
        total_equipment_cost=total_equipment_cost,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )
