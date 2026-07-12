"""Handler for adjusting a fighter's counter value by a delta.

Unlike :func:`handle_counter_spend` (a decrement-with-reason that leaves a
refundable spend record), this is a plain post-battle adjustment: add or
subtract from the running counter value, clamped at zero, with a CampaignAction
for the audit trail.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.content.models import ContentCounter
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListFighter, ListFighterCounter
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)


@dataclass
class FighterCounterAdjustResult:
    """Result of adjusting a fighter's counter value."""

    fighter: ListFighter
    counter: ContentCounter
    applied: int
    new_value: int
    campaign_action: Optional[CampaignAction]


@traced("handle_fighter_adjust_counter")
@transaction.atomic
def handle_fighter_adjust_counter(
    *,
    user,
    fighter: ListFighter,
    counter: ContentCounter,
    delta: int,
    battle=None,
) -> Optional[FighterCounterAdjustResult]:
    """
    Adjust a fighter's counter value by ``delta`` (positive or negative),
    clamped to a minimum of zero. Creates the ``ListFighterCounter`` row on
    demand and writes a CampaignAction (optionally attached to ``battle``) in
    campaign mode.

    A ``delta`` that produces no real change (0, or a decrement below an
    already-zero value) is a no-op and returns ``None``.
    """
    if not delta:
        return None

    lst = fighter.list

    fighter_counter = (
        ListFighterCounter.objects.select_for_update()
        .filter(fighter=fighter, counter=counter)
        .first()
    )
    current = fighter_counter.value if fighter_counter else 0
    new_value = max(0, current + delta)
    applied = new_value - current
    if applied == 0:
        return None

    if fighter_counter:
        fighter_counter.value = new_value
        fighter_counter.save_with_user(user=user)
    else:
        fighter_counter = ListFighterCounter.objects.create_with_user(
            user=user,
            fighter=fighter,
            counter=counter,
            value=new_value,
            owner=lst.owner,
        )

    campaign_action = None
    if lst.campaign:
        verb = "gained" if applied > 0 else "lost"
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            battle=battle,
            description=f"{fighter.name} {verb} {abs(applied)} {counter.name}",
            outcome=f"{counter.name}: {new_value}",
        )

    return FighterCounterAdjustResult(
        fighter=fighter,
        counter=counter,
        applied=applied,
        new_value=new_value,
        campaign_action=campaign_action,
    )
