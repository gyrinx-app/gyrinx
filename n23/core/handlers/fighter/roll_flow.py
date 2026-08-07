"""Handlers for roll-flow operations (spend a counter, roll on a table).

A roll flow (ContentRollFlow) lets a fighter spend counter points to roll on
a roll table and gain the matching row — e.g. a Spyrer spending 4 Kill Count
to roll on the Power Boost table. The gained row is recorded as a
ListFighterRollResult, which is both a mod source and a rating-cost source,
mirroring the advancement pattern.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from gyrinx.tracing import traced
from n23.content.models import ContentRollFlow, ContentRollTableRow
from n23.core.cost.propagation import Delta, propagate_from_fighter
from n23.core.models.action import ListAction, ListActionType
from n23.core.models.campaign import CampaignAction
from n23.core.models.list import (
    ListFighter,
    ListFighterCounter,
    ListFighterRollResult,
)

logger = logging.getLogger(__name__)


@dataclass
class RollFlowResult:
    """Result of applying a roll-flow outcome to a fighter."""

    roll_result: ListFighterRollResult
    fighter: ListFighter
    rating_increase: int
    counter_cost: int
    outcome: str

    update_action: ListAction
    campaign_action: CampaignAction | None


@dataclass
class RollResultDeletionResult:
    """Result of removing a roll result from a fighter."""

    roll_result: ListFighterRollResult
    fighter: ListFighter
    rating_decrease: int
    counter_refund: int

    update_action: ListAction
    campaign_action: CampaignAction | None


@traced("handle_roll_flow")
@transaction.atomic
def handle_roll_flow(
    *,
    user,
    fighter: ListFighter,
    flow: ContentRollFlow,
    row: ContentRollTableRow,
    rolled_value: int,
    campaign_action_id: UUID | None = None,
    roll_token: UUID | None = None,
    notes: str = "",
) -> RollFlowResult | None:
    """
    Apply a roll-flow outcome: deduct the counter, record the result,
    propagate the rating increase, and write ledger/campaign actions.

    Args:
        user: The user performing the flow.
        fighter: The fighter spending the counter.
        flow: The ContentRollFlow being used.
        row: The ContentRollTableRow matched by the roll.
        rolled_value: The combined roll value (for the outcome description).
        campaign_action_id: Optional existing CampaignAction (the dice roll)
            to link. Also used as an idempotency key.
        roll_token: Optional idempotency token from the roll step, used when
            there is no campaign action to key on (non-campaign lists).
        notes: Optional notes stored on the result.

    Returns:
        RollFlowResult, or None if this roll already produced a result
        (idempotent double-submit case).

    Raises:
        ValidationError: If the fighter is a stash fighter or the counter
            value is insufficient.
    """
    lst = fighter.list

    # Idempotency: a single roll produces at most one result. Campaign rolls
    # are keyed by their CampaignAction; non-campaign rolls by the roll token
    # minted at the roll step.
    if campaign_action_id or roll_token:
        existing_query = Q()
        if campaign_action_id:
            existing_query |= Q(campaign_action_id=campaign_action_id)
        if roll_token:
            existing_query |= Q(roll_token=roll_token)
        existing_result = ListFighterRollResult.objects.filter(existing_query).first()
        if existing_result:
            if existing_result.fighter != fighter:
                logger.warning(
                    "Roll (action %s / token %s) already linked to different fighter %s",
                    campaign_action_id,
                    roll_token,
                    existing_result.fighter.id,
                )
            return None

    if fighter.is_stash:
        raise ValidationError(
            f"Stash fighters cannot use roll flows. "
            f"Fighter '{fighter.name}' is a stash fighter."
        )

    # Lock the counter row (if it exists) and re-check affordability
    fighter_counter = (
        ListFighterCounter.objects.select_for_update()
        .filter(fighter=fighter, counter=flow.counter)
        .first()
    )
    current_value = fighter_counter.value if fighter_counter else 0
    if current_value < flow.cost:
        raise ValidationError(
            f"{fighter.name} has insufficient {flow.counter.name}. "
            f"Required: {flow.cost}, Available: {current_value}"
        )

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Bucket by the fighter's own stash-ness, matching facts_from_db.
    is_stash = fighter.is_stash

    # Deduct the counter. The affordability guard above means a missing
    # counter row can only pass when flow.cost == 0, so there is nothing to
    # deduct unless the row exists.
    if flow.cost and fighter_counter:
        fighter_counter.value = current_value - flow.cost
        fighter_counter.save_with_user(user=user)

    rating_increase = row.rating_increase
    outcome = (
        f"{fighter.name} rolled {rolled_value} on {flow.roll_table.name}: {row.name}"
    )

    # Link or create the CampaignAction
    campaign_action = None
    if campaign_action_id:
        try:
            # Scoped to the fighter's list so a roll result can never be
            # attached to another list's campaign action
            campaign_action = CampaignAction.objects.get(
                id=campaign_action_id, list=lst
            )
        except CampaignAction.DoesNotExist:
            raise ValidationError(
                f"Campaign action {campaign_action_id} not found"
            ) from None
        campaign_action.outcome = outcome
        campaign_action.save()
    elif lst.campaign:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=(
                f"{fighter.name} spent {flow.cost} {flow.counter.name} on {flow.name}"
            ),
            outcome=outcome,
        )

    roll_result = ListFighterRollResult.objects.create(
        owner=lst.owner,
        fighter=fighter,
        row=row,
        flow=flow,
        counter=flow.counter,
        counter_cost=flow.cost,
        rating_increase=rating_increase,
        notes=notes,
        campaign_action=campaign_action,
        roll_token=roll_token,
    )

    # Propagate the rating increase (push path; the pull path reads the
    # stored rating_increase via cost_int/facts_from_db)
    if rating_increase != 0:
        propagate_from_fighter(fighter, Delta(delta=rating_increase, list=lst))

    update_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighterRollResult",
        subject_id=roll_result.id,
        description=f"{fighter.name} gained {row.name} (+{rating_increase}¢)",
        list_fighter=fighter,
        rating_delta=rating_increase if not is_stash else 0,
        stash_delta=rating_increase if is_stash else 0,
        credits_delta=0,  # Roll flows cost counter points, not credits
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    return RollFlowResult(
        roll_result=roll_result,
        fighter=fighter,
        rating_increase=rating_increase,
        counter_cost=flow.cost,
        outcome=outcome,
        update_action=update_action,
        campaign_action=campaign_action,
    )


@traced("handle_roll_result_deletion")
@transaction.atomic
def handle_roll_result_deletion(
    *,
    user,
    fighter: ListFighter,
    roll_result: ListFighterRollResult,
) -> RollResultDeletionResult:
    """
    Remove a roll result: archive it, reverse the rating increase, and
    refund the counter points that were spent.

    Raises:
        ValidationError: If the result is already archived or belongs to a
            different fighter.
    """
    lst = fighter.list

    if roll_result.fighter_id != fighter.id:
        raise ValidationError("Roll result does not belong to this fighter.")
    if roll_result.archived:
        raise ValidationError("Roll result has already been removed.")

    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Bucket by the fighter's own stash-ness, matching facts_from_db.
    is_stash = fighter.is_stash

    rating_decrease = roll_result.rating_increase
    counter_refund = roll_result.counter_cost

    # Refund the counter points that were spent
    if counter_refund and roll_result.counter:
        fighter_counter = (
            ListFighterCounter.objects.select_for_update()
            .filter(fighter=fighter, counter=roll_result.counter)
            .first()
        )
        if fighter_counter:
            fighter_counter.value += counter_refund
            fighter_counter.save_with_user(user=user)
        else:
            ListFighterCounter.objects.create_with_user(
                user=user,
                fighter=fighter,
                counter=roll_result.counter,
                value=counter_refund,
                owner=lst.owner,
            )

    roll_result.archive()

    if rating_decrease != 0:
        propagate_from_fighter(fighter, Delta(delta=-rating_decrease, list=lst))

    update_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighterRollResult",
        subject_id=roll_result.id,
        description=f"{fighter.name} removed {roll_result.row.name} (-{rating_decrease}¢)",
        list_fighter=fighter,
        rating_delta=-rating_decrease if not is_stash else 0,
        stash_delta=-rating_decrease if is_stash else 0,
        credits_delta=0,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    campaign_action = None
    if lst.campaign:
        refund_text = (
            f", refunding {counter_refund} {roll_result.counter.name}"
            if counter_refund and roll_result.counter
            else ""
        )
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"{fighter.name} removed {roll_result.row.name}{refund_text}",
        )

    return RollResultDeletionResult(
        roll_result=roll_result,
        fighter=fighter,
        rating_decrease=rating_decrease,
        counter_refund=counter_refund,
        update_action=update_action,
        campaign_action=campaign_action,
    )
