"""Handlers for battle crews (#1346).

The one piece of real business logic is *locking* a crew: at battle start we
roll the random-selection spec once, draw that many fighters from the eligible
pool, freeze every attendee as a :class:`CrewMember`, and record a
battle-linked campaign action. There are no re-rolls after this. Simple CRUD
(create/edit the draft recipe, manage loadouts and extras) stays in the views.
"""

import logging
from dataclasses import dataclass
from random import Random  # nosec B311 - game dice, not crypto
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.crew import Crew, CrewMember, roll_selection_spec
from gyrinx.core.models.list import ListFighter
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)


def eligible_crew_fighters(lst):
    """Fighters in ``lst`` eligible to be picked or drawn for a crew.

    Active state, not the stash, not archived — mirrors the single-fighter
    add-injury eligibility and the original crew-template work (#1360).
    Scenario-specific restrictions (no Leader, one Champion, …) are surfaced
    as warnings later, not enforced here.
    """
    return ListFighter.objects.filter(
        list=lst,
        archived=False,
        content_fighter__is_stash=False,
        injury_state=ListFighter.ACTIVE,
    )


@dataclass
class CrewLockResult:
    """Result of locking (drawing) a crew."""

    crew: Crew
    chosen_count: int
    random_count: int
    roll_detail: str
    campaign_action: Optional[CampaignAction]


@traced("handle_crew_lock")
@transaction.atomic
def handle_crew_lock(*, user, crew: Crew, rng=None) -> CrewLockResult:
    """
    Lock a draft crew at battle start.

    Creates a :class:`CrewMember` for every chosen fighter, then rolls
    ``crew.random_spec`` and draws that many more at random from the eligible
    pool (excluding the already-chosen). Sets the crew LOCKED and writes a
    battle-linked CampaignAction. Idempotency: a crew that is already locked
    raises rather than drawing again (no re-rolls).

    Pass ``rng`` (any object with ``randint``/``shuffle``) for deterministic
    tests.
    """
    if crew.is_locked:
        raise ValidationError("This crew has already been locked.")

    lst = crew.list
    rng = rng or Random()  # nosec B311 - game dice, not crypto

    chosen = list(crew.chosen_fighters.all())
    chosen_ids = {f.pk for f in chosen}
    for fighter in chosen:
        CrewMember.objects.create_with_user(
            user=user,
            owner=lst.owner,
            crew=crew,
            list_fighter=fighter,
            was_random=False,
        )

    random_count, roll_detail = roll_selection_spec(crew.random_spec, rng=rng)
    drawn = []
    if random_count > 0:
        pool = list(eligible_crew_fighters(lst).exclude(pk__in=chosen_ids))
        rng.shuffle(pool)
        drawn = pool[:random_count]
        for fighter in drawn:
            CrewMember.objects.create_with_user(
                user=user,
                owner=lst.owner,
                crew=crew,
                list_fighter=fighter,
                was_random=True,
            )

    crew.status = Crew.LOCKED
    crew.save_with_user(user=user)

    campaign_action = None
    campaign = crew.battle.campaign
    if campaign:
        outcome_parts = [f"{len(chosen)} chosen"]
        if random_count:
            drew = f"{len(drawn)} random"
            if roll_detail:
                drew += f" ({roll_detail})"
            outcome_parts.append(drew)
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=campaign,
            list=lst,
            battle=crew.battle,
            description=f"Crew locked for {lst.name}: {crew.method_label()}",
            outcome=", ".join(outcome_parts),
        )

    return CrewLockResult(
        crew=crew,
        chosen_count=len(chosen),
        random_count=len(drawn),
        roll_detail=roll_detail,
        campaign_action=campaign_action,
    )
