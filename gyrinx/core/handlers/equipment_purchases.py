"""
Business logic handlers for equipment purchase operations.

These handlers extract the core business logic from views, making them
directly testable without HTTP machinery. All handlers are transactional
and raise ValidationError on failure.
"""

from dataclasses import dataclass
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentUpgrade,
    ContentFighter,
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
from gyrinx.tracker import track

User = get_user_model()


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
    else:
        # We are adding to stash, so make sure there's stash fighter
        crew = lst.ensure_stash()

    # Create the equipment assignment - this will trigger automatic vehicle creation
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=crew,
        content_equipment=vehicle_equipment,
    )

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
    # Calculate cost BEFORE reassignment (assignment should still be on from_fighter)
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
