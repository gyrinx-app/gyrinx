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
        try:
            campaign_action = CampaignAction.objects.get(id=campaign_action_id)
        except CampaignAction.DoesNotExist:
            raise ValidationError(f"Campaign action {campaign_action_id} not found")
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


@dataclass
class FighterAdvancementDeletionResult:
    """Result of deleting (archiving) a fighter advancement."""

    advancement_id: UUID
    advancement_description: str
    xp_restored: int
    cost_decrease: int
    description: str
    list_action: Optional[ListAction]

    # Warnings for the user
    warnings: list[str]


@transaction.atomic
def handle_fighter_advancement_deletion(
    *,
    user,
    fighter: ListFighter,
    advancement: ListFighterAdvancement,
) -> FighterAdvancementDeletionResult:
    """
    Handle deletion (archiving) of a fighter advancement.

    This handler reverses the effects of an advancement:
    1. Archives the advancement
    2. Restores XP to the fighter
    3. Reduces rating/stash by cost_increase
    4. For mod-based stat advancements: stat change disappears automatically
    5. For legacy stat advancements: recalculates the override field
    6. For skill advancements: removes skill and recalculates category_override
    7. For equipment advancements: warns user to remove equipment manually
    8. For other advancements: just archives (no side effects)

    Args:
        user: The user performing the deletion
        fighter: The fighter whose advancement is being deleted
        advancement: The advancement to delete

    Returns:
        FighterAdvancementDeletionResult with deletion details

    Raises:
        ValidationError: If the advancement cannot be deleted
    """
    lst = fighter.list
    warnings = []

    # Validate the advancement belongs to this fighter
    if advancement.fighter_id != fighter.id:
        raise ValidationError("Advancement does not belong to this fighter")

    # Validate the advancement is not already archived
    if advancement.archived:
        raise ValidationError("Advancement is already archived")

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Determine where cost delta should go
    is_stash_linked = _is_fighter_stash_linked(fighter)

    # Store advancement details before archiving
    advancement_id = advancement.id
    advancement_description = str(advancement)
    xp_restored = advancement.xp_cost
    cost_decrease = advancement.cost_increase

    # Reverse the advancement effects based on type
    if advancement.advancement_type == ListFighterAdvancement.ADVANCEMENT_STAT:
        _reverse_stat_advancement(advancement, fighter, warnings)
    elif advancement.advancement_type == ListFighterAdvancement.ADVANCEMENT_SKILL:
        _reverse_skill_advancement(advancement, fighter, warnings)
    elif advancement.advancement_type == ListFighterAdvancement.ADVANCEMENT_EQUIPMENT:
        # Equipment advancements require manual removal
        warnings.append(
            "Equipment from this advancement must be removed manually before "
            "the advancement can be fully reversed."
        )
    # ADVANCEMENT_OTHER has no effects to reverse

    # Restore XP to fighter
    fighter.xp_current += xp_restored
    fighter.save()

    # Archive the advancement
    advancement.archive()

    # Build description
    description = f"Removed advancement: {advancement_description} (XP +{xp_restored}, Cost -{cost_decrease}¢)"

    # Create ListAction with negative cost delta
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighterAdvancement",
        subject_id=advancement_id,
        description=description,
        list_fighter=fighter,
        rating_delta=-cost_decrease if not is_stash_linked else 0,
        stash_delta=-cost_decrease if is_stash_linked else 0,
        credits_delta=0,  # Advancements don't affect credits
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    return FighterAdvancementDeletionResult(
        advancement_id=advancement_id,
        advancement_description=advancement_description,
        xp_restored=xp_restored,
        cost_decrease=cost_decrease,
        description=description,
        list_action=list_action,
        warnings=warnings,
    )


def _reverse_stat_advancement(
    advancement: ListFighterAdvancement,
    fighter: ListFighter,
    warnings: list[str],
) -> None:
    """
    Reverse a stat advancement.

    For mod-based advancements (uses_mod_system=True), the stat change
    disappears automatically when the advancement is archived.

    For legacy advancements (uses_mod_system=False), we need to recalculate
    the override field based on remaining advancements.
    """
    if advancement.uses_mod_system:
        # Mod-based: stat change disappears automatically when archived
        return

    # Legacy advancement: need to recalculate the override field
    stat_name = advancement.stat_increased
    override_field = f"{stat_name}_override"

    # Count remaining non-archived stat advancements for this stat
    # (excluding the one being deleted)
    remaining_count = (
        ListFighterAdvancement.objects.filter(
            fighter=fighter,
            archived=False,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
            stat_increased=stat_name,
            uses_mod_system=False,  # Only count legacy advancements
        )
        .exclude(id=advancement.id)
        .count()
    )

    if remaining_count == 0:
        # No more legacy advancements for this stat, clear the override
        setattr(fighter, override_field, None)
    else:
        # Recalculate the override based on remaining advancements
        base_value = getattr(fighter.content_fighter, stat_name)
        new_value = _calculate_stat_value(base_value, remaining_count)
        setattr(fighter, override_field, new_value)

    fighter.save()


def _calculate_stat_value(base_value: str, improvement_count: int) -> str:
    """
    Calculate the new stat value after a number of improvements.

    Args:
        base_value: The base stat value (e.g., "3+", "4", '4"')
        improvement_count: Number of improvements to apply

    Returns:
        The improved stat value
    """
    if not base_value:
        return base_value

    if "+" in base_value:
        # Target roll stats (WS, BS, Initiative, etc.) - lower is better
        base_numeric = int(base_value.replace("+", ""))
        new_value = base_numeric - improvement_count
        return f"{new_value}+"
    elif '"' in base_value:
        # Distance stats (Movement) - higher is better
        base_numeric = int(base_value.replace('"', ""))
        new_value = base_numeric + improvement_count
        return f'{new_value}"'
    else:
        # Numeric stats (S, T, W, A) - higher is better
        try:
            base_numeric = int(base_value)
            new_value = base_numeric + improvement_count
            return str(new_value)
        except ValueError:
            return base_value


def _reverse_skill_advancement(
    advancement: ListFighterAdvancement,
    fighter: ListFighter,
    warnings: list[str],
) -> None:
    """
    Reverse a skill advancement.

    Removes the skill from the fighter and recalculates category_override
    if this was a promotion advancement.
    """
    # Remove the skill
    if advancement.skill:
        fighter.skills.remove(advancement.skill)

    # Handle promotion reversals
    if advancement.advancement_choice in [
        "skill_promote_specialist",
        "skill_promote_champion",
    ]:
        _recalculate_category_override(fighter, advancement)


def _recalculate_category_override(
    fighter: ListFighter,
    advancement_being_deleted: ListFighterAdvancement,
) -> None:
    """
    Recalculate the fighter's category_override after a promotion advancement is deleted.

    Looks at all remaining non-archived skill advancements with promotion choices
    and sets category_override to the highest remaining promotion level.

    Promotion hierarchy:
    - Champion > Specialist > None

    Args:
        fighter: The fighter to recalculate
        advancement_being_deleted: The advancement being deleted (excluded from calculation)
    """
    # Import here to avoid circular imports
    from gyrinx.models import FighterCategoryChoices

    # Find remaining promotion advancements (excluding the one being deleted)
    remaining_promotions = ListFighterAdvancement.objects.filter(
        fighter=fighter,
        archived=False,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        advancement_choice__in=["skill_promote_specialist", "skill_promote_champion"],
    ).exclude(id=advancement_being_deleted.id)

    # Check for Champion promotions first (highest)
    has_champion = remaining_promotions.filter(
        advancement_choice="skill_promote_champion"
    ).exists()

    if has_champion:
        fighter.category_override = FighterCategoryChoices.CHAMPION
    else:
        # Check for Specialist promotions
        has_specialist = remaining_promotions.filter(
            advancement_choice="skill_promote_specialist"
        ).exists()

        if has_specialist:
            fighter.category_override = FighterCategoryChoices.SPECIALIST
        else:
            # No promotions remaining, clear the override
            fighter.category_override = None

    fighter.save()
