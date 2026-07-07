"""Handlers for free-form counter spends (spend counter points, no roll flow).

A counter spend lets a fighter spend points from a counter without invoking a
roll table — the user picks the amount and records why and to what end. Unlike
a roll flow it has no dice, no roll-table row, and no rating impact: the spend
only decrements the counter and leaves an auditable, refundable record
(ListFighterCounterSpend), plus a CampaignAction in campaign mode.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from gyrinx.content.models import ContentCounter
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    ListFighter,
    ListFighterCounter,
    ListFighterCounterSpend,
)
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)


@dataclass
class CounterSpendResult:
    """Result of recording a free-form counter spend."""

    spend: ListFighterCounterSpend
    fighter: ListFighter
    amount: int

    update_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]


@dataclass
class CounterSpendRemovalResult:
    """Result of removing (refunding) a counter spend."""

    spend: ListFighterCounterSpend
    fighter: ListFighter
    refund: int

    update_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]


@traced("handle_counter_spend")
@transaction.atomic
def handle_counter_spend(
    *,
    user,
    fighter: ListFighter,
    counter: ContentCounter,
    amount: int,
    reason: str = "",
) -> CounterSpendResult:
    """
    Record a free-form counter spend: deduct the counter, store the purpose,
    and write ledger/campaign actions.

    Args:
        user: The user performing the spend.
        fighter: The fighter spending the counter.
        counter: The ContentCounter being spent.
        amount: How many points to spend (must be >= 1 and <= current value).
        reason: The purpose of the spend (required, non-blank).

    Returns:
        CounterSpendResult.

    Raises:
        ValidationError: If the fighter is a stash fighter, the amount is not
            positive, the purpose is blank, or the counter value is
            insufficient.
    """
    lst = fighter.list

    if fighter.is_stash:
        raise ValidationError(
            f"Stash fighters cannot spend counters. "
            f"Fighter '{fighter.name}' is a stash fighter."
        )

    if amount < 1:
        raise ValidationError("Spend amount must be at least 1.")

    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A purpose is required.")

    # Lock the counter row (if it exists) and re-check affordability
    fighter_counter = (
        ListFighterCounter.objects.select_for_update()
        .filter(fighter=fighter, counter=counter)
        .first()
    )
    current_value = fighter_counter.value if fighter_counter else 0
    if amount > current_value:
        raise ValidationError(
            f"{fighter.name} has insufficient {counter.name}. "
            f"Requested: {amount}, Available: {current_value}"
        )

    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Deduct the counter. The affordability guard above (amount >= 1 and
    # amount <= current_value) means fighter_counter must exist here.
    fighter_counter.value = current_value - amount
    fighter_counter.save_with_user(user=user)

    # Mirror to a CampaignAction in campaign mode. The purpose is included in
    # the description.
    campaign_action = None
    if lst.campaign:
        description = f"{fighter.name} spent {amount} {counter.name}"
        if reason:
            description = f"{description} — {reason}"
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=description,
        )

    spend = ListFighterCounterSpend.objects.create(
        owner=lst.owner,
        fighter=fighter,
        counter=counter,
        amount=amount,
        reason=reason,
        campaign_action=campaign_action,
    )

    update_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighterCounterSpend",
        subject_id=spend.id,
        description=f"{fighter.name} spent {amount} {counter.name}",
        list_fighter=fighter,
        rating_delta=0,
        stash_delta=0,
        credits_delta=0,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    return CounterSpendResult(
        spend=spend,
        fighter=fighter,
        amount=amount,
        update_action=update_action,
        campaign_action=campaign_action,
    )


@traced("handle_counter_spend_removal")
@transaction.atomic
def handle_counter_spend_removal(
    *,
    user,
    fighter: ListFighter,
    spend: ListFighterCounterSpend,
) -> CounterSpendRemovalResult:
    """
    Remove a counter spend: archive it and refund the points that were spent.

    Raises:
        ValidationError: If the spend is already archived or belongs to a
            different fighter.
    """
    lst = fighter.list

    # Lock the spend row and re-read it under the lock, so two concurrent
    # removals can't both pass the archived guard and double-refund.
    spend = ListFighterCounterSpend.objects.select_for_update().get(pk=spend.pk)

    if spend.fighter_id != fighter.id:
        raise ValidationError("Counter spend does not belong to this fighter.")
    if spend.archived:
        raise ValidationError("Counter spend has already been removed.")

    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    refund = spend.amount

    # Refund the counter points that were spent
    if refund and spend.counter:
        fighter_counter = (
            ListFighterCounter.objects.select_for_update()
            .filter(fighter=fighter, counter=spend.counter)
            .first()
        )
        if fighter_counter:
            fighter_counter.value += refund
            fighter_counter.save_with_user(user=user)
        else:
            ListFighterCounter.objects.create_with_user(
                user=user,
                fighter=fighter,
                counter=spend.counter,
                value=refund,
                owner=lst.owner,
            )
    elif refund and not spend.counter:
        # The counter was deleted (SET_NULL), so there is nothing to refund
        # into. Surface it rather than silently dropping the points.
        logger.warning(
            "Cannot refund %s points for counter spend %s: counter was deleted.",
            refund,
            spend.id,
        )

    spend.archive()

    counter_name = spend.counter.name if spend.counter else "counter"

    update_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighterCounterSpend",
        subject_id=spend.id,
        description=f"{fighter.name} refunded {refund} {counter_name}",
        list_fighter=fighter,
        rating_delta=0,
        stash_delta=0,
        credits_delta=0,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    campaign_action = None
    if lst.campaign:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"{fighter.name} refunded {refund} {counter_name}",
        )

    return CounterSpendRemovalResult(
        spend=spend,
        fighter=fighter,
        refund=refund,
        update_action=update_action,
        campaign_action=campaign_action,
    )
