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
    whole_gang: bool = False
    # Hand-picked fighters dropped at lock because they were no longer eligible
    # (archived / stashed / killed / in recovery since the recipe was built).
    skipped_ineligible: int = 0


@traced("handle_crew_lock")
@transaction.atomic
def handle_crew_lock(*, user, crew: Crew, rng=None) -> CrewLockResult:
    """
    Lock a draft crew at battle start.

    Creates a :class:`CrewMember` for every chosen fighter, then rolls
    ``crew.random_spec`` and draws that many more at random from the eligible
    pool (excluding the already-chosen). A crew with neither chosen fighters nor
    a random spec is a "whole gang" crew: the entire eligible roster attends.
    Sets the crew LOCKED and writes a battle-linked CampaignAction. Idempotency:
    a crew that is already locked raises rather than drawing again (no re-rolls).

    Pass ``rng`` (any object with ``randint``/``shuffle``) for deterministic
    tests.
    """
    # Lock the crew row for the duration of the draw so two concurrent lock
    # POSTs can't both pass the guard and race on the member INSERTs.
    crew = Crew.objects.select_for_update().get(pk=crew.pk)
    if crew.is_locked:
        raise ValidationError("This crew has already been locked.")

    lst = crew.list
    rng = rng or Random()  # nosec B311 - game dice, not crypto

    # Re-check eligibility at lock time: a fighter hand-picked while the recipe
    # was being built may since have been archived, stashed, killed, or put in
    # recovery. The rulebook excludes fighters who can't take part from every
    # selection method, so drop them here rather than enrolling them.
    eligible = eligible_crew_fighters(lst)
    eligible_ids = set(eligible.values_list("pk", flat=True))
    picked = list(crew.chosen_fighters.all())
    chosen = [f for f in picked if f.pk in eligible_ids]
    skipped_ineligible = len(picked) - len(chosen)
    chosen_ids = {f.pk for f in chosen}
    random_spec = (crew.random_spec or "").strip()

    # Whole gang: no explicit picks and no random draw means the whole eligible
    # roster attends (rulebook: Custom Selection with no number). Judged from the
    # original recipe — picks that are all now ineligible make an empty custom
    # crew, not a whole-gang one.
    whole_gang = not picked and not random_spec

    non_random = chosen if not whole_gang else list(eligible)
    for fighter in non_random:
        CrewMember.objects.create_with_user(
            user=user,
            owner=lst.owner,
            crew=crew,
            list_fighter=fighter,
            was_random=False,
        )

    random_count, roll_detail = (0, "")
    drawn = []
    if not whole_gang:
        random_count, roll_detail = roll_selection_spec(random_spec, rng=rng)
        if random_count > 0:
            pool = list(eligible.exclude(pk__in=chosen_ids))
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

    if whole_gang:
        outcome = f"{len(non_random)} fighters (whole gang)"
    else:
        outcome_parts = [f"{len(chosen)} chosen"]
        if random_count:
            drew = f"{len(drawn)} random"
            if roll_detail:
                drew += f" ({roll_detail})"
            outcome_parts.append(drew)
        outcome = ", ".join(outcome_parts)

    # Battle.campaign is a non-nullable FK, so there is always a campaign to log.
    campaign_action = CampaignAction.objects.create(
        user=user,
        owner=user,
        campaign=crew.battle.campaign,
        list=lst,
        battle=crew.battle,
        description=f"Crew selected for {lst.name}: {crew.method_label()}",
        outcome=outcome,
    )

    return CrewLockResult(
        crew=crew,
        chosen_count=len(non_random),
        random_count=len(drawn),
        roll_detail=roll_detail,
        campaign_action=campaign_action,
        whole_gang=whole_gang,
        skipped_ineligible=skipped_ineligible,
    )
