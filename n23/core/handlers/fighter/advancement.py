"""Handler for fighter advancement operations."""

import logging
from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction

from gyrinx.tracing import traced
from n23.content.models import (
    ContentAdvancementAssignment,
    ContentFighter,
    ContentPromotionPath,
    ContentSkill,
)
from n23.core.cost.propagation import Delta, propagate_from_fighter
from n23.core.models.action import ListAction, ListActionType
from n23.core.models.campaign import CampaignAction
from n23.core.models.list import (
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
    update_action: ListAction  # UPDATE_FIGHTER for cost_increase
    equipment_action: ListAction | None  # ADD_EQUIPMENT for equipment advancements

    campaign_action: CampaignAction | None

    # What was created/modified (for logging)
    equipment_assignment: ListFighterEquipmentAssignment | None


@traced("handle_fighter_advancement")
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
    stat_increased: str | None = None,
    skill: ContentSkill | None = None,
    equipment_assignment: ContentAdvancementAssignment | None = None,
    promotion_path: ContentPromotionPath | None = None,
    promotion_target: ContentFighter | None = None,
    description: str | None = None,
    # Campaign action linking
    campaign_action_id: UUID | None = None,
) -> FighterAdvancementResult | None:
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
        skill: For skill advancements (and skill-bundling promotions), the ContentSkill
        equipment_assignment: For equipment advancements, the ContentAdvancementAssignment
        promotion_path: For promotion advancements, the ContentPromotionPath taken
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

    # Validate fighter is not a direct stash fighter (stash fighters cannot advance)
    # Note: Child fighters linked to stash (vehicles/exotic beasts with source_assignment
    # pointing to stash-owned equipment) CAN advance - their costs go to stash_delta.
    # This check only rejects direct stash fighters (is_stash=True).
    if fighter.is_stash:
        raise ValidationError(
            f"Stash fighters cannot receive advancements. "
            f"Fighter '{fighter.name}' is a stash fighter."
        )

    # Validate XP sufficiency
    if fighter.xp_current < xp_cost:
        raise ValidationError(
            f"Fighter {fighter.name} has insufficient XP. "
            f"Required: {xp_cost}, Available: {fighter.xp_current}"
        )

    # Availability is the handler's job, not just the offering layer's: a crafted
    # confirm/select URL (or programmatic call) must not apply a promotion the fighter
    # isn't eligible for — including re-buying a path already taken (promotion changes
    # the fighter's category, so a taken path no longer matches).
    if promotion_path is not None and not promotion_path.is_available_to_fighter(
        fighter
    ):
        raise ValidationError(
            f"Promotion '{promotion_path.name}' is not available to {fighter.name}."
        )
    if promotion_target is not None and (
        promotion_path is None
        or not promotion_path.resolve_targets(fighter)
        .filter(id=promotion_target.id)
        .exists()
    ):
        raise ValidationError(
            "The chosen promotion target is not one of this path's targets."
        )

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Determine where cost delta should go:
    # - Stash-linked fighters affect stash_current
    # - Regular fighters affect rating_current
    # Bucket by the fighter's own stash-ness, matching facts_from_db — a
    # child fighter (vehicle/beast) counts toward rating even when its
    # parent equipment sits on the stash.
    is_stash = fighter.is_stash

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
        promotion_path=promotion_path,
        promotion_target=promotion_target,
        description=description,
    )

    # Generate outcome description
    outcome = _generate_outcome_description(
        advancement_type=advancement_type,
        advancement_choice=advancement_choice,
        stat_increased=stat_increased,
        skill=skill,
        equipment_assignment=equipment_assignment,
        promotion_path=promotion_path,
        promotion_target=promotion_target,
        description=description,
    )

    # Handle CampaignAction linking/creation
    campaign_action = None
    if campaign_action_id:
        # Link to existing campaign action and update outcome
        try:
            campaign_action = CampaignAction.objects.get(id=campaign_action_id)
        except CampaignAction.DoesNotExist:
            raise ValidationError(
                f"Campaign action {campaign_action_id} not found"
            ) from None
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

    # Propagate the cost increase
    if cost_increase != 0:
        propagate_from_fighter(fighter, Delta(delta=cost_increase, list=lst))

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
        rating_delta=cost_increase if not is_stash else 0,
        stash_delta=cost_increase if is_stash else 0,
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
    stat_increased: str | None,
    skill: ContentSkill | None,
    equipment_assignment: ContentAdvancementAssignment | None,
    promotion_path: ContentPromotionPath | None = None,
    promotion_target: ContentFighter | None = None,
    description: str | None,
) -> str:
    """Generate a human-readable outcome description for the advancement."""
    # Import here to avoid circular imports
    from n23.core.forms.advancement import AdvancementTypeForm

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

    elif advancement_type == ListFighterAdvancement.ADVANCEMENT_PROMOTION:
        outcome = promotion_path.name if promotion_path else "Promoted"
        if promotion_target:
            outcome += f" — now counts as {promotion_target.type}"
        if skill:
            outcome += f", gaining {skill.name} skill"
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
    list_action: ListAction

    # Warnings for the user
    warnings: list[str]


@traced("handle_fighter_advancement_deletion")
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
    # Bucket by the fighter's own stash-ness, matching facts_from_db — a
    # child fighter (vehicle/beast) counts toward rating even when its
    # parent equipment sits on the stash.
    is_stash = fighter.is_stash

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
    elif advancement.advancement_type == ListFighterAdvancement.ADVANCEMENT_PROMOTION:
        _reverse_promotion_advancement(advancement, fighter, warnings)
    elif advancement.advancement_type == ListFighterAdvancement.ADVANCEMENT_EQUIPMENT:
        # Equipment advancements require manual removal
        warnings.append(
            "Equipment added by this advancement must be removed manually. "
            "The advancement has been reversed, but the equipment remains on the fighter."
        )
    # ADVANCEMENT_OTHER has no effects to reverse

    # Restore XP to fighter
    fighter.xp_current += xp_restored
    fighter.save()

    # Propagate the cost decrease
    if cost_decrease != 0:
        propagate_from_fighter(fighter, Delta(delta=-cost_decrease, list=lst))

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
        rating_delta=-cost_decrease if not is_stash else 0,
        stash_delta=-cost_decrease if is_stash else 0,
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


@traced("_reverse_stat_advancement")
def _reverse_stat_advancement(
    advancement: ListFighterAdvancement,
    fighter: ListFighter,
    warnings: list[str],
) -> None:
    """
    Reverse a stat advancement.

    The stat change disappears on its own when the advancement is archived,
    because the value is computed from the mod system at display time.

    A handful of pre-Track-B advancements still carry ``uses_mod_system=False``
    and contribute no mod. Their effect was baked into a ``<stat>_override``
    column, which Track C2 turned into a plain override row and Track C3
    stopped reading. Recalculating the column here would write somewhere
    nothing reads, so these are left alone — but the stat then stays put while
    the XP and cost come back, which is worth saying out loud.
    """
    if advancement.uses_mod_system:
        return

    warnings.append(
        f"{fighter.name}'s {advancement.stat_increased.replace('_', ' ')} was "
        "not changed: this advancement predates the current stat system, so "
        "its improvement is held as a manual override. Edit the fighter's "
        "stats if it should come back down."
    )


@traced("_reverse_skill_advancement")
def _reverse_skill_advancement(
    advancement: ListFighterAdvancement,
    fighter: ListFighter,
    warnings: list[str],
) -> None:
    """
    Reverse a skill advancement.

    Removes the skill from the fighter and recalculates category_override if this was a
    legacy-era promotion (stored as a skill advancement with a skill_promote_* choice).
    """
    # Remove the skill
    if advancement.skill:
        fighter.skills.remove(advancement.skill)

    # Handle promotion reversals (legacy rows resolve via the static choice map)
    if advancement.resolved_promotion():
        _recalculate_category_override(fighter, advancement)


@traced("_reverse_promotion_advancement")
def _reverse_promotion_advancement(
    advancement: ListFighterAdvancement,
    fighter: ListFighter,
    warnings: list[str],
) -> None:
    """
    Reverse a promotion advancement: remove any bundled skill, recalculate the category.
    """
    if advancement.skill:
        fighter.skills.remove(advancement.skill)
    _recalculate_category_override(fighter, advancement)


@traced("_recalculate_category_override")
def _recalculate_category_override(
    fighter: ListFighter,
    advancement_being_deleted: ListFighterAdvancement,
) -> None:
    """
    Recalculate the fighter's promotion state after a promotion advancement is deleted.

    Rank-driven: every remaining non-archived advancement that resolves as a promotion
    (data-driven rows via their ContentPromotionPath rank; legacy skill_promote_* rows via
    the static map) competes, and the highest rank wins — for both the category override
    and the type-change access pointer. No promotions remaining clears both.

    Args:
        fighter: The fighter to recalculate
        advancement_being_deleted: The advancement being deleted (excluded from calculation)
    """
    remaining = ListFighterAdvancement.objects.filter(
        fighter=fighter,
        archived=False,
        advancement_type__in=[
            ListFighterAdvancement.ADVANCEMENT_SKILL,
            ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        ],
    ).exclude(id=advancement_being_deleted.id)

    best = None
    best_with_target = None
    for adv in remaining:
        resolved = adv.resolved_promotion()
        if not resolved or not resolved.to_category:
            continue
        if best is None or resolved.rank > best.rank:
            best = resolved
        # The pointer competes only among promotions that HAVE a target — a
        # higher-ranked relabel must not wipe the counts-as of a still-held
        # type change.
        if resolved.target is not None and (
            best_with_target is None or resolved.rank > best_with_target.rank
        ):
            best_with_target = resolved

    fighter.category_override = best.to_category if best else None
    fighter.promoted_content_fighter = (
        best_with_target.target if best_with_target else None
    )
    fighter.save()
