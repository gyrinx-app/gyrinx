"""
Business logic handlers for equipment purchase operations.

These handlers extract the core business logic from views, making them
directly testable without HTTP machinery. All handlers are transactional
and raise ValidationError on failure.
"""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.content.models import (
    ContentEquipmentUpgrade,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    VirtualWeaponProfile,
)
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)


@dataclass
class EquipmentPurchaseResult:
    """Result of a successful equipment purchase."""

    assignment: ListFighterEquipmentAssignment
    total_cost: int
    description: str
    list_action: ListAction
    campaign_action: Optional[CampaignAction]


@dataclass
class AccessoryPurchaseResult:
    """Result of a successful weapon accessory purchase."""

    assignment: ListFighterEquipmentAssignment
    accessory_cost: int
    description: str
    list_action: ListAction
    campaign_action: Optional[CampaignAction]


@dataclass
class WeaponProfilePurchaseResult:
    """Result of a successful weapon profile purchase."""

    assignment: ListFighterEquipmentAssignment
    profile_cost: int
    description: str
    list_action: ListAction
    campaign_action: Optional[CampaignAction]


@dataclass
class EquipmentUpgradeResult:
    """Result of a successful equipment upgrade change."""

    assignment: ListFighterEquipmentAssignment
    cost_difference: int
    description: str
    list_action: ListAction
    campaign_action: Optional[CampaignAction]


@transaction.atomic
def handle_equipment_purchase(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
) -> EquipmentPurchaseResult:
    """
    Handle the purchase of equipment for a fighter.

    This handler performs the following operations atomically:
    1. Saves the assignment and M2M relationships
    2. Calculates total cost including profiles, accessories, and upgrades
    3. Spends credits if in campaign mode
    4. Creates CampaignAction if in campaign mode
    5. Creates ListAction to track the purchase

    Args:
        user: The user making the purchase
        lst: The list the fighter belongs to
        fighter: The fighter receiving the equipment
        assignment: The equipment assignment (must be saved with form.save() before calling)

    Returns:
        EquipmentPurchaseResult with assignment, cost, description, and actions

    Raises:
        ValidationError: If the purchase cannot be completed (e.g., insufficient credits)
    """
    # Refetch to get the full cost including profiles, accessories, and upgrades
    assignment.refresh_from_db()
    total_cost = assignment.cost_int()

    # Build these beforehand so we get the credit values right
    is_stash = fighter.is_stash
    la_args = dict(
        rating_delta=total_cost if not is_stash else 0,
        stash_delta=total_cost if is_stash else 0,
        credits_delta=-total_cost if lst.is_campaign_mode else 0,
        rating_before=lst.rating_current,
        stash_before=lst.stash_current,
        credits_before=lst.credits_current,
    )

    # Handle credit spending for campaign mode
    campaign_action = None
    if lst.is_campaign_mode:
        description = f"Bought {assignment.content_equipment.name} for {fighter.name} ({total_cost}¢)"
        lst.spend_credits(
            total_cost,
            description=f"Buying {assignment.content_equipment.name}",
        )

        # Create campaign action
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=description,
            outcome=f"Credits remaining: {lst.credits_current}¢",
        )
    else:
        description = f"Added {assignment.content_equipment.name} to {fighter.name} ({total_cost}¢)"

    # Create list action
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=description,
        list_fighter=fighter,
        list_fighter_equipment_assignment=assignment,
        **la_args,
    )

    return EquipmentPurchaseResult(
        assignment=assignment,
        total_cost=total_cost,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )


@transaction.atomic
def handle_accessory_purchase(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
    accessory: ContentWeaponAccessory,
) -> AccessoryPurchaseResult:
    """
    Handle the purchase of a weapon accessory for an equipment assignment.

    This handler performs the following operations atomically:
    1. Calculates the cost of the accessory
    2. Spends credits if in campaign mode
    3. Creates CampaignAction if in campaign mode
    4. Adds the accessory to the assignment
    5. Creates ListAction to track the purchase

    Args:
        user: The user making the purchase
        lst: The list the fighter belongs to
        fighter: The fighter whose equipment is being upgraded
        assignment: The equipment assignment to add the accessory to
        accessory: The weapon accessory to add

    Returns:
        AccessoryPurchaseResult with assignment, cost, description, and actions

    Raises:
        ValidationError: If the purchase cannot be completed (e.g., insufficient credits)
    """
    # Calculate the cost of this accessory
    accessory_cost = assignment.accessory_cost_int(accessory)

    # Build these beforehand so we get the credit values right
    is_stash = fighter.is_stash
    la_args = dict(
        rating_delta=accessory_cost if not is_stash else 0,
        stash_delta=accessory_cost if is_stash else 0,
        credits_delta=-accessory_cost if lst.is_campaign_mode else 0,
        rating_before=lst.rating_current,
        stash_before=lst.stash_current,
        credits_before=lst.credits_current,
    )

    # Handle credit spending for campaign mode
    campaign_action = None
    if lst.is_campaign_mode:
        lst.spend_credits(accessory_cost, description=f"Buying {accessory.name}")

        # Create campaign action
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"Bought {accessory.name} for {assignment.content_equipment.name} on {fighter.name} ({accessory_cost}¢)",
            outcome=f"Credits remaining: {lst.credits_current}¢",
        )

    # Add the accessory to the assignment
    assignment.weapon_accessories_field.add(accessory)

    description = f"Bought {accessory.name} for {assignment.content_equipment.name} on {fighter.name} ({accessory_cost}¢)"

    # Create ListAction to track the accessory addition
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=description,
        list_fighter_equipment_assignment=assignment,
        **la_args,
    )

    return AccessoryPurchaseResult(
        assignment=assignment,
        accessory_cost=accessory_cost,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )


@transaction.atomic
def handle_weapon_profile_purchase(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
    profile: ContentWeaponProfile,
) -> WeaponProfilePurchaseResult:
    """
    Handle the purchase of a weapon profile for an equipment assignment.

    This handler performs the following operations atomically:
    1. Calculates the cost of the profile
    2. Spends credits if in campaign mode
    3. Creates CampaignAction if in campaign mode
    4. Adds the profile to the assignment
    5. Creates ListAction to track the purchase

    Args:
        user: The user making the purchase
        lst: The list the fighter belongs to
        fighter: The fighter whose equipment is being upgraded
        assignment: The equipment assignment to add the profile to
        profile: The weapon profile to add

    Returns:
        WeaponProfilePurchaseResult with assignment, cost, description, and actions

    Raises:
        ValidationError: If the purchase cannot be completed (e.g., insufficient credits)
    """
    # Calculate the cost of this profile
    virtual_profile = VirtualWeaponProfile(profile=profile)
    profile_cost = assignment.profile_cost_int(virtual_profile)

    # Build these beforehand so we get the credit values right
    is_stash = fighter.is_stash
    la_args = dict(
        rating_delta=profile_cost if not is_stash else 0,
        stash_delta=profile_cost if is_stash else 0,
        credits_delta=-profile_cost if lst.is_campaign_mode else 0,
        rating_before=lst.rating_current,
        stash_before=lst.stash_current,
        credits_before=lst.credits_current,
    )

    # Handle credit spending for campaign mode
    campaign_action = None
    if lst.is_campaign_mode:
        lst.spend_credits(profile_cost, description=f"Buying {profile.name}")

        # Create campaign action
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"Bought {profile.name} for {assignment.content_equipment.name} on {fighter.name} ({profile_cost}¢)",
            outcome=f"Credits remaining: {lst.credits_current}¢",
        )

    # Add the profile to the assignment
    assignment.weapon_profiles_field.add(profile)

    description = f"Bought {profile.name} for {assignment.content_equipment.name} on {fighter.name} ({profile_cost}¢)"

    # Create ListAction to track the profile addition
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=description,
        list_fighter_equipment_assignment=assignment,
        **la_args,
    )

    return WeaponProfilePurchaseResult(
        assignment=assignment,
        profile_cost=profile_cost,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )


@transaction.atomic
def handle_equipment_upgrade(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
    new_upgrades: list[ContentEquipmentUpgrade],
) -> EquipmentUpgradeResult:
    """
    Handle the change of equipment upgrades for an equipment assignment.

    This handler performs the following operations atomically:
    1. Calculates the cost difference between old and new upgrades
    2. Spends credits if in campaign mode and cost increased
    3. Creates CampaignAction if in campaign mode and cost increased
    4. Updates the assignment's upgrades
    5. Creates ListAction to track the change

    Args:
        user: The user making the change
        lst: The list the fighter belongs to
        fighter: The fighter whose equipment is being upgraded
        assignment: The equipment assignment to update
        new_upgrades: The new list of upgrades (can be empty to remove all)

    Returns:
        EquipmentUpgradeResult with assignment, cost difference, description, and actions

    Raises:
        ValidationError: If the purchase cannot be completed (e.g., insufficient credits)
    """
    # Get current upgrades cost
    old_upgrade_cost = assignment.upgrade_cost_int()

    # Calculate new upgrade cost
    new_upgrade_cost = (
        sum(assignment._upgrade_cost_with_override(u) for u in new_upgrades)
        if new_upgrades
        else 0
    )

    cost_difference = new_upgrade_cost - old_upgrade_cost

    # Build these beforehand so we get the credit values right
    # Note: cost_difference can be negative (removing upgrades) or zero
    is_stash = fighter.is_stash
    la_args = dict(
        rating_delta=cost_difference if not is_stash else 0,
        stash_delta=cost_difference if is_stash else 0,
        credits_delta=-cost_difference
        if lst.is_campaign_mode and cost_difference > 0
        else 0,
        rating_before=lst.rating_current,
        stash_before=lst.stash_current,
        credits_before=lst.credits_current,
    )

    # Handle credit spending for campaign mode (only if cost increased)
    campaign_action = None
    if lst.is_campaign_mode and cost_difference > 0:
        lst.spend_credits(
            cost_difference,
            description=f"Buying upgrades for {assignment.content_equipment.name}",
        )

        # Create campaign action
        upgrade_names = ", ".join([u.name for u in new_upgrades])
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"Bought upgrades ({upgrade_names}) for {assignment.content_equipment.name} on {fighter.name} ({cost_difference}¢)",
            outcome=f"Credits remaining: {lst.credits_current}¢",
        )

    # Update the upgrades
    assignment.upgrades_field.set(new_upgrades)

    # Create ListAction to track the upgrade change
    if new_upgrades:
        upgrade_names = ", ".join([u.name for u in new_upgrades])
        description = f"Bought upgrades ({upgrade_names}) for {assignment.content_equipment.name} on {fighter.name} ({cost_difference}¢)"
    else:
        description = f"Removed upgrades from {assignment.content_equipment.name} on {fighter.name}"

    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment.id,
        description=description,
        list_fighter_equipment_assignment=assignment,
        **la_args,
    )

    return EquipmentUpgradeResult(
        assignment=assignment,
        cost_difference=cost_difference,
        description=description,
        list_action=list_action,
        campaign_action=campaign_action,
    )
