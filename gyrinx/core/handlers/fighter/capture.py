"""Handlers for fighter capture, release, return, and sell operations."""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.cost.propagation import Delta, propagate_from_fighter
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    CapturedFighter,
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.tracing import traced


@dataclass
class FighterCaptureResult:
    """Result of capturing a fighter."""

    captured_fighter_record: CapturedFighter
    fighter: ListFighter
    capturing_list: List
    original_list: List
    fighter_cost: int
    equipment_removed: list[tuple[str, int]]  # [(assignment_id, cost), ...]
    capture_list_action: Optional[ListAction]
    equipment_removal_actions: list[Optional[ListAction]]
    campaign_action: Optional[CampaignAction]


@dataclass
class FighterSellResult:
    """Result of selling a captured fighter to guilders."""

    captured_fighter_record: CapturedFighter
    fighter: ListFighter
    capturing_list: List
    sale_price: int
    sell_list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]


@dataclass
class FighterReturnResult:
    """Result of returning a fighter to their original owner."""

    fighter: ListFighter
    original_list: List
    capturing_list: List
    ransom_amount: int
    fighter_cost: int
    original_list_action: Optional[ListAction]
    capturing_list_action: Optional[ListAction]
    original_campaign_action: Optional[CampaignAction]
    capturing_campaign_action: Optional[CampaignAction]


@dataclass
class FighterReleaseResult:
    """Result of releasing a captured fighter."""

    fighter: ListFighter
    original_list: List
    fighter_cost: int
    release_list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]


@traced("handle_fighter_capture")
@transaction.atomic
def handle_fighter_capture(
    *,
    user,
    fighter: ListFighter,
    capturing_list: List,
) -> FighterCaptureResult:
    """
    Handle the capture of a fighter by another gang.

    This handler performs the following operations atomically:
    1. Removes child fighter equipment (if fighter is a child of equipment)
    2. Creates REMOVE_EQUIPMENT ListActions for each removed equipment
    3. Calculates fighter cost BEFORE capture
    4. Creates CapturedFighter record
    5. Creates CAPTURE_FIGHTER ListAction on original gang
    6. Creates CampaignAction if in campaign mode

    Args:
        user: The user performing the capture
        fighter: The fighter being captured
        capturing_list: The gang capturing the fighter

    Returns:
        FighterCaptureResult with all created objects

    Note:
        - Fighter rating is reduced by fighter_cost on original gang
        - Child fighters have 0 cost, but their parent's equipment has cost
        - Parent equipment is deleted when child is captured
        - No credits are exchanged during capture
    """
    original_list = fighter.list
    equipment_removed = []
    equipment_removal_actions = []

    # 1. Find all assignments where this fighter is the child
    # (e.g., exotic beast linked to handler's equipment)
    child_assignments = ListFighterEquipmentAssignment.objects.filter(
        child_fighter=fighter
    ).select_related("list_fighter", "content_equipment")

    for assignment in child_assignments:
        parent_fighter = assignment.list_fighter
        equipment_cost = assignment.cost_int()
        assignment_id = str(assignment.id)
        equipment_name = assignment.content_equipment.name

        # Capture before values for equipment removal
        rating_before = original_list.rating_current
        stash_before = original_list.stash_current
        credits_before = original_list.credits_current

        # Calculate deltas (removing equipment from parent fighter)
        is_stash = parent_fighter.is_stash
        rating_delta = -equipment_cost if not is_stash else 0
        stash_delta = -equipment_cost if is_stash else 0
        credits_delta = 0

        # Unlink the child fighter first to prevent cascade issues
        assignment.child_fighter = None
        assignment.save()

        # Delete the assignment
        assignment.delete()

        # Track what was removed
        equipment_removed.append((assignment_id, equipment_cost))

        # Create REMOVE_EQUIPMENT ListAction
        removal_action = original_list.create_action(
            user=user,
            action_type=ListActionType.REMOVE_EQUIPMENT,
            subject_app="core",
            subject_type="ListFighterEquipmentAssignment",
            subject_id=assignment_id,
            description=f"Removed {equipment_name} from {parent_fighter.name} "
            f"due to capture of {fighter.name} ({equipment_cost}¢)",
            list_fighter=parent_fighter,
            rating_delta=rating_delta,
            stash_delta=stash_delta,
            credits_delta=credits_delta,
            rating_before=rating_before,
            stash_before=stash_before,
            credits_before=credits_before,
        )
        equipment_removal_actions.append(removal_action)

    # 2. Calculate fighter cost BEFORE creating capture record
    # (Once captured, should_have_zero_cost returns True and cost_int returns 0)
    fighter_cost = fighter.cost_int()

    # 3. Capture before values for capture action
    rating_before = original_list.rating_current
    stash_before = original_list.stash_current
    credits_before = original_list.credits_current

    # 4. Create CapturedFighter record
    captured_record = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=capturing_list,
        owner=user,
    )

    # Propagate the cost reduction (fighter_cost → 0)
    if fighter_cost > 0:
        propagate_from_fighter(fighter, Delta(delta=-fighter_cost, list=original_list))

    # 5. Calculate deltas for capture action
    # Child fighters: fighter_cost is 0, so rating_delta is 0
    # Regular fighters: rating decreases by fighter_cost
    rating_delta = -fighter_cost
    stash_delta = 0
    credits_delta = 0

    # 6. Create CampaignAction if in campaign mode
    campaign_action = None
    if original_list.is_campaign_mode:
        total_equipment_cost = sum(cost for _, cost in equipment_removed)
        total_cost = fighter_cost + total_equipment_cost

        description = f"{fighter.name} was captured by {capturing_list.name}"
        if equipment_removed:
            description += f" (linked equipment removed: {total_equipment_cost}¢)"

        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=original_list.campaign,
            list=original_list,
            description=description,
            outcome=f"Rating reduced by {total_cost}¢",
        )

    # 7. Create CAPTURE_FIGHTER ListAction
    capture_action = original_list.create_action(
        user=user,
        action_type=ListActionType.CAPTURE_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=f"{fighter.name} captured by {capturing_list.name} ({fighter_cost}¢)",
        list_fighter=fighter,
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    return FighterCaptureResult(
        captured_fighter_record=captured_record,
        fighter=fighter,
        capturing_list=capturing_list,
        original_list=original_list,
        fighter_cost=fighter_cost,
        equipment_removed=equipment_removed,
        capture_list_action=capture_action,
        equipment_removal_actions=equipment_removal_actions,
        campaign_action=campaign_action,
    )


@traced("handle_fighter_sell_to_guilders")
@transaction.atomic
def handle_fighter_sell_to_guilders(
    *,
    user,
    captured_fighter: CapturedFighter,
    sale_price: int,
) -> FighterSellResult:
    """
    Handle selling a captured fighter to guilders.

    This handler performs the following operations atomically:
    1. Marks CapturedFighter as sold_to_guilders
    2. Adds sale credits to capturing gang
    3. Creates SELL_FIGHTER ListAction on capturing gang
    4. Creates CampaignAction if in campaign mode

    Args:
        user: The user performing the sale
        captured_fighter: The CapturedFighter record
        sale_price: Credits received for selling

    Returns:
        FighterSellResult with updated objects

    Note:
        - Credits are added to capturing gang
        - Fighter remains with original gang but is marked as sold
        - Original gang rating remains at 0 for this fighter (permanent)
    """
    fighter = captured_fighter.fighter
    capturing_list = captured_fighter.capturing_list

    # Capture before values
    rating_before = capturing_list.rating_current
    stash_before = capturing_list.stash_current
    credits_before = capturing_list.credits_current

    # Mark as sold (this updates sold_to_guilders and sold_at)
    captured_fighter.sell_to_guilders(credits=sale_price)

    # Calculate deltas (only credits change on capturing gang)
    rating_delta = 0
    stash_delta = 0
    credits_delta = sale_price

    # Create CampaignAction if in campaign mode
    campaign_action = None
    if capturing_list.is_campaign_mode:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=capturing_list.campaign,
            list=capturing_list,
            description=f"Sold {fighter.name} from {fighter.list.name} to guilders"
            + (f" for {sale_price}¢" if sale_price > 0 else ""),
            outcome=f"+{sale_price}¢ (to {capturing_list.credits_current + credits_delta}¢)",
        )

    # Create SELL_FIGHTER ListAction with update_credits=True
    sell_action = capturing_list.create_action(
        user=user,
        action_type=ListActionType.SELL_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=f"Sold {fighter.name} to guilders for {sale_price}¢",
        list_fighter=fighter,
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
        update_credits=True,
    )

    return FighterSellResult(
        captured_fighter_record=captured_fighter,
        fighter=fighter,
        capturing_list=capturing_list,
        sale_price=sale_price,
        sell_list_action=sell_action,
        campaign_action=campaign_action,
    )


@traced("handle_fighter_return_to_owner")
@transaction.atomic
def handle_fighter_return_to_owner(
    *,
    user,
    captured_fighter: CapturedFighter,
    ransom_amount: int = 0,
) -> FighterReturnResult:
    """
    Handle returning a captured fighter to their original owner.

    This handler performs the following operations atomically:
    1. Validates original gang can afford ransom (if > 0)
    2. Transfers ransom credits between gangs (if ransom > 0)
    3. Deletes CapturedFighter record
    4. Creates RETURN_FIGHTER ListAction on original gang (rating restoration)
    5. Creates RETURN_FIGHTER ListAction on capturing gang (if ransom > 0)
    6. Creates CampaignAction(s) if in campaign mode

    Args:
        user: The user performing the return
        captured_fighter: The CapturedFighter record
        ransom_amount: Credits paid by original gang to capturing gang (default 0)

    Returns:
        FighterReturnResult with created objects

    Raises:
        ValidationError: If original gang cannot afford ransom in campaign mode

    Note:
        - Original gang regains rating equal to fighter_cost
        - If ransom > 0, original gang pays credits, capturing gang receives
    """
    from django.core.exceptions import ValidationError

    fighter = captured_fighter.fighter
    original_list = fighter.list
    capturing_list = captured_fighter.capturing_list

    # Validate ransom affordability in campaign mode
    if ransom_amount > 0 and original_list.is_campaign_mode:
        if original_list.credits_current < ransom_amount:
            raise ValidationError(
                f"{original_list.name} doesn't have enough credits to pay the ransom. "
                f"Available: {original_list.credits_current}¢, Required: {ransom_amount}¢"
            )

    # Capture before values for BOTH lists before any changes
    orig_rating_before = original_list.rating_current
    orig_stash_before = original_list.stash_current
    orig_credits_before = original_list.credits_current

    cap_rating_before = capturing_list.rating_current
    cap_stash_before = capturing_list.stash_current
    cap_credits_before = capturing_list.credits_current

    # Delete capture record (restores fighter - should_have_zero_cost becomes False)
    captured_fighter.delete()

    # Refresh fighter to clear cached properties
    fighter.refresh_from_db()

    # Calculate restored fighter cost (after capture record deleted)
    fighter_cost = fighter.cost_int()

    # Propagate the cost restoration
    if fighter_cost > 0:
        propagate_from_fighter(fighter, Delta(delta=fighter_cost, list=original_list))

    # Calculate deltas for original gang (rating increases, credits decrease if ransom)
    orig_rating_delta = fighter_cost
    orig_stash_delta = 0
    orig_credits_delta = -ransom_amount if ransom_amount > 0 else 0

    # Calculate deltas for capturing gang (only credits change, if ransom)
    cap_rating_delta = 0
    cap_stash_delta = 0
    cap_credits_delta = ransom_amount if ransom_amount > 0 else 0

    # Create CampaignActions if in campaign mode
    original_campaign_action = None
    capturing_campaign_action = None

    if original_list.is_campaign_mode:
        if ransom_amount > 0:
            original_campaign_action = CampaignAction.objects.create(
                user=user,
                owner=user,
                campaign=original_list.campaign,
                list=original_list,
                description=f"Paid {ransom_amount}¢ ransom to {capturing_list.name} for {fighter.name}",
                outcome=f"-{ransom_amount}¢, rating +{fighter_cost}¢",
            )
        else:
            original_campaign_action = CampaignAction.objects.create(
                user=user,
                owner=user,
                campaign=original_list.campaign,
                list=original_list,
                description=f"{fighter.name} returned from {capturing_list.name}",
                outcome=f"Rating +{fighter_cost}¢",
            )

    if ransom_amount > 0 and capturing_list.is_campaign_mode:
        capturing_campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=capturing_list.campaign,
            list=capturing_list,
            description=f"Received {ransom_amount}¢ ransom for returning {fighter.name} to {original_list.name}",
            outcome=f"+{ransom_amount}¢",
        )

    # Create ListAction on original gang (rating restoration, credits deducted if ransom)
    original_action = original_list.create_action(
        user=user,
        action_type=ListActionType.RETURN_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=f"{fighter.name} returned from {capturing_list.name}"
        + (f" for {ransom_amount}¢ ransom" if ransom_amount > 0 else "")
        + f" (rating +{fighter_cost}¢)",
        list_fighter=fighter,
        rating_delta=orig_rating_delta,
        stash_delta=orig_stash_delta,
        credits_delta=orig_credits_delta,
        rating_before=orig_rating_before,
        stash_before=orig_stash_before,
        credits_before=orig_credits_before,
        update_credits=True,
    )

    # Create ListAction on capturing gang only if ransom > 0 (credits added)
    capturing_action = None
    if ransom_amount > 0:
        capturing_action = capturing_list.create_action(
            user=user,
            action_type=ListActionType.RETURN_FIGHTER,
            subject_app="core",
            subject_type="ListFighter",
            subject_id=fighter.id,
            description=f"Returned {fighter.name} to {original_list.name} for {ransom_amount}¢ ransom",
            list_fighter=fighter,
            rating_delta=cap_rating_delta,
            stash_delta=cap_stash_delta,
            credits_delta=cap_credits_delta,
            rating_before=cap_rating_before,
            stash_before=cap_stash_before,
            credits_before=cap_credits_before,
            update_credits=True,
        )

    return FighterReturnResult(
        fighter=fighter,
        original_list=original_list,
        capturing_list=capturing_list,
        ransom_amount=ransom_amount,
        fighter_cost=fighter_cost,
        original_list_action=original_action,
        capturing_list_action=capturing_action,
        original_campaign_action=original_campaign_action,
        capturing_campaign_action=capturing_campaign_action,
    )


@traced("handle_fighter_release")
@transaction.atomic
def handle_fighter_release(
    *,
    user,
    captured_fighter: CapturedFighter,
) -> FighterReleaseResult:
    """
    Handle releasing a captured fighter without ransom.

    This handler performs the following operations atomically:
    1. Deletes CapturedFighter record
    2. Creates RELEASE_FIGHTER ListAction on original gang
    3. Creates CampaignAction if in campaign mode

    Args:
        user: The user performing the release
        captured_fighter: The CapturedFighter record

    Returns:
        FighterReleaseResult with created objects

    Note:
        - No credits exchanged
        - Original gang regains rating equal to fighter_cost
        - Functionally similar to return with ransom=0, but different action type
    """
    fighter = captured_fighter.fighter
    original_list = fighter.list
    capturing_list = captured_fighter.capturing_list

    # Capture before values
    rating_before = original_list.rating_current
    stash_before = original_list.stash_current
    credits_before = original_list.credits_current

    # Delete capture record (restores fighter)
    captured_fighter.delete()

    # Refresh fighter to clear cached properties
    fighter.refresh_from_db()

    # Calculate restored fighter cost
    fighter_cost = fighter.cost_int()

    # Propagate the cost restoration
    if fighter_cost > 0:
        propagate_from_fighter(fighter, Delta(delta=fighter_cost, list=original_list))

    # Calculate deltas (only rating changes)
    rating_delta = fighter_cost
    stash_delta = 0
    credits_delta = 0

    # Create CampaignAction if in campaign mode
    campaign_action = None
    if original_list.is_campaign_mode:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=original_list.campaign,
            list=capturing_list,  # Action is on capturing list (they released)
            description=f"Released {fighter.name} back to {original_list.name} without ransom",
            outcome=f"{original_list.name} rating +{fighter_cost}¢",
        )

    # Create RELEASE_FIGHTER ListAction on original gang
    release_action = original_list.create_action(
        user=user,
        action_type=ListActionType.RELEASE_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=f"{fighter.name} released by {capturing_list.name} (rating +{fighter_cost}¢)",
        list_fighter=fighter,
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    return FighterReleaseResult(
        fighter=fighter,
        original_list=original_list,
        fighter_cost=fighter_cost,
        release_list_action=release_action,
        campaign_action=campaign_action,
    )
