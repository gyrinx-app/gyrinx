"""Handler for fighter kill operations in campaign mode."""

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
from gyrinx.tracing import traced


@dataclass
class FighterKillResult:
    """Result of killing a fighter in campaign mode."""

    fighter: ListFighter
    fighter_cost_before: int
    equipment_count: int
    list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]
    description: str


@traced("handle_fighter_kill")
@transaction.atomic
def handle_fighter_kill(
    *,
    user,
    lst: List,
    fighter: ListFighter,
) -> FighterKillResult:
    """
    Handle fighter death in campaign mode.

    This handler performs the following operations atomically:
    1. Captures before values for ListAction
    2. Finds stash fighter
    3. Transfers ALL equipment to stash (creates new assignments)
    4. Deletes original equipment assignments
    5. Marks fighter as DEAD
    6. Sets fighter cost_override = 0
    7. Creates UPDATE_FIGHTER ListAction for death
    8. Creates CampaignAction if in campaign

    The fighter's cost goes from X to 0, reducing rating by X.
    Equipment transfers from fighter to stash don't change overall wealth,
    but equipment is preserved in the stash for potential re-use.

    Args:
        user: User performing the kill
        lst: List containing the fighter
        fighter: Fighter being killed (must not be stash, must be campaign mode)

    Returns:
        FighterKillResult with all operation details

    Raises:
        ValueError: If fighter is stash or list is not in campaign mode
    """
    # Validate preconditions
    if not lst.is_campaign_mode:
        raise ValueError("Fighters can only be killed in campaign mode")

    if fighter.is_stash:
        raise ValueError("Cannot kill the stash")

    # Capture BEFORE values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate fighter cost before death (includes equipment)
    fighter_cost_before = fighter.cost_int()

    # Find the stash fighter for this list
    stash_fighter = lst.listfighter_set.filter(content_fighter__is_stash=True).first()

    # Transfer equipment to stash
    equipment_count = 0
    equipment_cost = 0
    if stash_fighter:
        equipment_assignments = fighter.listfighterequipmentassignment_set.all()
        equipment_count = equipment_assignments.count()
        # Calculate equipment cost before we delete assignments
        equipment_cost = sum(a.cost_int() for a in equipment_assignments)

        for assignment in equipment_assignments:
            # Create new assignment for stash with same equipment
            new_assignment = ListFighterEquipmentAssignment(
                list_fighter=stash_fighter,
                content_equipment=assignment.content_equipment,
                cost_override=assignment.cost_override,
                total_cost_override=assignment.total_cost_override,
                from_default_assignment=assignment.from_default_assignment,
            )
            new_assignment.save()

            # Copy over M2M relationships
            if assignment.weapon_profiles_field.exists():
                new_assignment.weapon_profiles_field.set(
                    assignment.weapon_profiles_field.all()
                )
            if assignment.weapon_accessories_field.exists():
                new_assignment.weapon_accessories_field.set(
                    assignment.weapon_accessories_field.all()
                )
            if assignment.upgrades_field.exists():
                new_assignment.upgrades_field.set(assignment.upgrades_field.all())

        # Delete all equipment assignments from the dead fighter
        equipment_assignments.delete()

    # Mark fighter as dead and set cost to 0
    fighter.injury_state = ListFighter.DEAD
    fighter.cost_override = 0
    fighter.save()

    # Build description
    equipment_desc = (
        " All equipment transferred to stash."
        if equipment_count > 0
        else " No equipment to transfer."
    )
    description = f"{fighter.name} was killed ({fighter_cost_before}¢).{equipment_desc}"

    # Create UPDATE_FIGHTER ListAction for death
    # Rating decreases by fighter's full cost (base + equipment)
    # Stash increases by equipment value (transferred there)
    # Net wealth change = -fighter_base_cost (equipment preserved in stash)
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=description,
        list_fighter=fighter,
        rating_delta=-fighter_cost_before,
        stash_delta=equipment_cost,
        credits_delta=0,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    # Create CampaignAction if this list is part of a campaign
    campaign_action = None
    if lst.campaign:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"Death: {fighter.name} was killed",
            outcome=f"{fighter.name} is permanently dead.{equipment_desc}",
        )

    return FighterKillResult(
        fighter=fighter,
        fighter_cost_before=fighter_cost_before,
        equipment_count=equipment_count,
        list_action=list_action,
        campaign_action=campaign_action,
        description=description,
    )
