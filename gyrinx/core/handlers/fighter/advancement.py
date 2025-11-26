"""Handler for fighter advancement operations."""

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction

from gyrinx.content.models import ContentAdvancementAssignment, ContentSkill
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    ListFighter,
    ListFighterAdvancement,
    ListFighterEquipmentAssignment,
)

logger = logging.getLogger(__name__)


@dataclass
class FighterAdvancementResult:
    """Result of applying a fighter advancement."""

    advancement: ListFighterAdvancement
    fighter: ListFighter
    cost_increase: int
    outcome: str

    # ListActions created
    update_action: Optional[ListAction]  # UPDATE_FIGHTER for cost_increase
    equipment_action: Optional[ListAction]  # ADD_EQUIPMENT for equipment advancements

    campaign_action: Optional[CampaignAction]

    # What was created/modified (for logging)
    equipment_assignment: Optional[ListFighterEquipmentAssignment]


def _is_fighter_stash_linked(fighter: ListFighter) -> bool:
    """
    Detect if a fighter's cost changes should go to stash instead of rating.

    A fighter is stash-linked if:
    1. It's directly a stash fighter (fighter.is_stash), OR
    2. It's a child fighter (vehicle/exotic beast) linked to equipment
       owned by a stash fighter

    Args:
        fighter: The fighter to check

    Returns:
        True if cost increases should go to stash_delta instead of rating_delta
    """
    # Direct stash fighter
    if fighter.is_stash:
        return True

    # Child fighter (vehicle/exotic beast) linked to stash via source_assignment
    if fighter.is_child_fighter:
        parent_assignment = fighter.source_assignment.first()
        if parent_assignment:
            return parent_assignment.list_fighter.is_stash

    return False


@transaction.atomic
def handle_fighter_advancement(
    *,
    user,
    fighter: ListFighter,
    advancement_type: str,
    xp_cost: int,
    cost_increase: int,
    advancement_choice: str,
    # Type-specific parameters (only one set should be provided)
    stat_increased: Optional[str] = None,
    skill: Optional[ContentSkill] = None,
    equipment_assignment: Optional[ContentAdvancementAssignment] = None,
    description: Optional[str] = None,
    # Campaign action linking
    campaign_action_id: Optional[UUID] = None,
) -> Optional[FighterAdvancementResult]:
    """
    Handle fighter advancement with ListAction tracking.

    Creates the ListFighterAdvancement, applies it to the fighter,
    creates appropriate ListAction(s) for cost tracking, and
    links/creates CampaignAction if in campaign mode.

    This handler owns ALL business logic for advancement application.

    Args:
        user: The user performing the advancement
        fighter: The fighter being advanced
        advancement_type: Type of advancement (ADVANCEMENT_STAT, etc.)
        xp_cost: XP cost of the advancement
        cost_increase: Credits added to fighter cost
        advancement_choice: The choice identifier from the advancement flow
        stat_increased: For stat advancements, which stat (e.g., "weapon_skill")
        skill: For skill advancements, the ContentSkill
        equipment_assignment: For equipment advancements, the ContentAdvancementAssignment
        description: For "other" advancements, free text description
        campaign_action_id: Optional existing CampaignAction to link

    Returns:
        FighterAdvancementResult with all created objects, or None if
        advancement already exists (idempotent case)

    Raises:
        ValidationError: If fighter has insufficient XP
    """
    lst = fighter.list

    # Idempotency check: if campaign_action_id provided, check for existing advancement
    if campaign_action_id:
        existing_advancement = ListFighterAdvancement.objects.filter(
            campaign_action_id=campaign_action_id
        ).first()

        if existing_advancement:
            if existing_advancement.fighter != fighter:
                logger.warning(
                    f"Campaign action {campaign_action_id} already linked to "
                    f"different fighter {existing_advancement.fighter.id}"
                )
            # Return None to signal idempotent case (already applied)
            return None

    # Validate XP sufficiency
    if fighter.xp_current < xp_cost:
        raise ValidationError(
            f"Fighter {fighter.name} has insufficient XP. "
            f"Required: {xp_cost}, Available: {fighter.xp_current}"
        )

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Determine where cost delta should go:
    # - Stash-linked fighters affect stash_current
    # - Regular fighters affect rating_current
    is_stash_linked = _is_fighter_stash_linked(fighter)

    # Create the advancement object
    advancement = ListFighterAdvancement(
        fighter=fighter,
        owner=user,
        advancement_type=advancement_type,
        xp_cost=xp_cost,
        cost_increase=cost_increase,
        advancement_choice=advancement_choice,
        stat_increased=stat_increased,
        skill=skill,
        equipment_assignment=equipment_assignment,
        description=description,
    )

    # Generate outcome description
    outcome = _generate_outcome_description(
        advancement_type=advancement_type,
        advancement_choice=advancement_choice,
        stat_increased=stat_increased,
        skill=skill,
        equipment_assignment=equipment_assignment,
        description=description,
    )

    # Handle CampaignAction linking/creation
    campaign_action = None
    if campaign_action_id:
        # Link to existing campaign action and update outcome
        campaign_action = CampaignAction.objects.get(id=campaign_action_id)
        advancement.campaign_action = campaign_action
        campaign_action.outcome = outcome
        campaign_action.save()
    elif lst.campaign:
        # Create new campaign action
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"{fighter.name} spent {xp_cost} XP to advance",
            outcome=outcome,
        )
        advancement.campaign_action = campaign_action

    # Save the advancement
    advancement.save()

    # Apply the advancement (modifies fighter stats/skills, creates equipment, deducts XP)
    advancement.apply_advancement()

    # For equipment advancements, find the created equipment assignment
    created_equipment = None
    if advancement_type == ListFighterAdvancement.ADVANCEMENT_EQUIPMENT:
        # The equipment assignment was just created by apply_advancement()
        # Find it by the equipment from the advancement assignment
        if equipment_assignment:
            created_equipment = (
                ListFighterEquipmentAssignment.objects.filter(
                    list_fighter=fighter,
                    content_equipment=equipment_assignment.equipment,
                )
                .order_by("-created")
                .first()
            )

    # Create UPDATE_FIGHTER ListAction for cost_increase
    update_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighterAdvancement",
        subject_id=advancement.id,
        description=f"{fighter.name} advanced: {outcome} (+{cost_increase}¢)",
        list_fighter=fighter,
        rating_delta=cost_increase if not is_stash_linked else 0,
        stash_delta=cost_increase if is_stash_linked else 0,
        credits_delta=0,  # Advancements cost XP, not credits
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    # For equipment advancements, create ADD_EQUIPMENT ListAction
    equipment_action = None
    if created_equipment:
        # The equipment cost is already accounted for in cost_increase, so deltas are 0
        # This action is for tracking/auditing purposes
        equipment_action = lst.create_action(
            user=user,
            action_type=ListActionType.ADD_EQUIPMENT,
            subject_app="core",
            subject_type="ListFighterEquipmentAssignment",
            subject_id=created_equipment.id,
            description=f"{fighter.name} gained {equipment_assignment} from advancement",
            list_fighter=fighter,
            list_fighter_equipment_assignment=created_equipment,
            rating_delta=0,  # Cost already tracked in UPDATE_FIGHTER action
            stash_delta=0,
            credits_delta=0,
            rating_before=lst.rating_current,  # Current values after first action
            stash_before=lst.stash_current,
            credits_before=lst.credits_current,
        )

    return FighterAdvancementResult(
        advancement=advancement,
        fighter=fighter,
        cost_increase=cost_increase,
        outcome=outcome,
        update_action=update_action,
        equipment_action=equipment_action,
        campaign_action=campaign_action,
        equipment_assignment=created_equipment,
    )


def _generate_outcome_description(
    *,
    advancement_type: str,
    advancement_choice: str,
    stat_increased: Optional[str],
    skill: Optional[ContentSkill],
    equipment_assignment: Optional[ContentAdvancementAssignment],
    description: Optional[str],
) -> str:
    """Generate a human-readable outcome description for the advancement."""
    # Import here to avoid circular imports
    from gyrinx.core.forms.advancement import AdvancementTypeForm

    if advancement_type == ListFighterAdvancement.ADVANCEMENT_STAT:
        stat_display = AdvancementTypeForm.all_stat_choices().get(
            f"stat_{stat_increased}", stat_increased or "Unknown"
        )
        return f"Improved {stat_display}"

    elif advancement_type == ListFighterAdvancement.ADVANCEMENT_SKILL:
        outcome = f"Gained {skill.name} skill" if skill else "Gained skill"
        # Check for promotion
        if advancement_choice in ["skill_promote_specialist", "skill_promote_champion"]:
            outcome += " and was promoted"
        return outcome

    elif advancement_type == ListFighterAdvancement.ADVANCEMENT_EQUIPMENT:
        return (
            f"Gained {equipment_assignment}"
            if equipment_assignment
            else "Gained equipment"
        )

    elif advancement_type == ListFighterAdvancement.ADVANCEMENT_OTHER:
        return f"Gained {description}" if description else "Other advancement"

    return "Advanced"
