"""Handlers for battle crews (#1346).

Two pieces of real business logic live here:

- **Saving a recipe** — applying a selection method to a crew, which means
  clearing whatever belongs to the *other* methods and reconciling the chosen
  :class:`CrewMember` rows with the player's picks.
- **Locking a crew** — at battle start we roll the random-selection spec once,
  draw that many fighters from the eligible pool, add them as members, and
  record a battle-linked campaign action. There are no re-rolls after this.

Simple CRUD (loadouts, extras) stays in the views.
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


@traced("handle_crew_recipe_save")
@transaction.atomic
def handle_crew_recipe_save(
    *,
    user,
    crew: Crew,
    method: str,
    custom_count=None,
    chosen_fighters=None,
    random_spec: str = "",
) -> Crew:
    """Save a crew's selection recipe under ``method``.

    Each method uses a different subset of the recipe, so the fields belonging
    to the other methods are cleared: switching Hybrid → Random nulls
    ``custom_count`` and drops the chosen members, switching → Custom blanks
    ``random_spec``. That is what keeps a contradictory recipe (an entirely
    random selection that also names fighters) unrepresentable.

    The crew's chosen :class:`CrewMember` rows are then reconciled with
    ``chosen_fighters``: members exist from selection time, not just after the
    lock. Drawn members are never touched here — only a draft crew is editable,
    and a draft has none.
    """
    crew.selection_method = method
    crew.custom_count = custom_count if method in (Crew.CUSTOM, Crew.HYBRID) else None
    crew.random_spec = random_spec if method in (Crew.RANDOM, Crew.HYBRID) else ""
    crew.save_with_user(user=user)

    # Random Selection names nobody, so any previous picks go.
    wanted = (
        set()
        if method == Crew.RANDOM
        else {f.pk for f in (chosen_fighters or []) if f is not None}
    )

    chosen = {
        m.list_fighter_id: m for m in crew.members.filter(source=CrewMember.CHOSEN)
    }
    stale = [m.pk for fighter_id, m in chosen.items() if fighter_id not in wanted]
    if stale:
        crew.members.filter(pk__in=stale).delete()

    # Exclude every current member, not just the chosen ones: a fighter already
    # on the crew must not get a second row (unique(crew, list_fighter)).
    present = set(crew.members.values_list("list_fighter_id", flat=True))
    for fighter_id in wanted - present:
        CrewMember.objects.create_with_user(
            user=user,
            owner_id=crew.list.owner_id,
            crew=crew,
            list_fighter_id=fighter_id,
            source=CrewMember.CHOSEN,
        )

    return crew


@dataclass
class CrewLockResult:
    """Result of locking (drawing) a crew."""

    crew: Crew
    chosen_count: int
    random_count: int
    roll_detail: str
    campaign_action: Optional[CampaignAction]
    whole_gang: bool = False
    # Chosen fighters dropped at lock because they were no longer eligible
    # (archived / stashed / killed / in recovery since the recipe was built).
    skipped_ineligible: int = 0


@traced("handle_crew_lock")
@transaction.atomic
def handle_crew_lock(*, user, crew: Crew, rng=None) -> CrewLockResult:
    """
    Lock a draft crew at battle start.

    The chosen members already exist (they are created when the recipe is
    saved), so this re-checks their eligibility, enrols the whole roster for a
    whole-gang crew, then rolls ``crew.random_spec`` and draws that many more at
    random from the eligible pool. Sets the crew LOCKED and writes a
    battle-linked CampaignAction. Idempotency: a crew that is already locked
    raises rather than drawing again (no re-rolls).

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

    eligible = eligible_crew_fighters(lst)
    eligible_ids = set(eligible.values_list("pk", flat=True))
    members = list(crew.members.all())

    # Whole gang: Custom Selection with no number in brackets and nobody named.
    # Judged before the eligibility sweep below — picks that have all since
    # become ineligible make an empty custom crew, not a whole-gang one.
    whole_gang = crew.is_whole_gang and not members

    # Re-check eligibility at lock time: a fighter chosen while the recipe was
    # being built may since have been archived, stashed, killed, or put in
    # recovery. The rulebook excludes fighters who can't take part from every
    # selection method, so drop them here rather than enrolling them.
    stale = [m.pk for m in members if m.list_fighter_id not in eligible_ids]
    skipped_ineligible = len(stale)
    if stale:
        crew.members.filter(pk__in=stale).delete()

    if whole_gang:
        for fighter in eligible:
            CrewMember.objects.create_with_user(
                user=user,
                owner_id=lst.owner_id,
                crew=crew,
                list_fighter=fighter,
                source=CrewMember.CHOSEN,
            )

    chosen_count = crew.members.count()

    random_count, roll_detail = (0, "")
    drawn = []
    if crew.selection_method in (Crew.RANDOM, Crew.HYBRID):
        random_count, roll_detail = roll_selection_spec(crew.random_spec, rng=rng)
        if random_count > 0:
            # Exclude everyone already on the crew, not just the chosen ones:
            # re-drawing a present fighter would trip unique(crew, list_fighter).
            present_ids = set(crew.members.values_list("list_fighter_id", flat=True))
            pool = list(eligible.exclude(pk__in=present_ids))
            rng.shuffle(pool)
            drawn = pool[:random_count]
            for fighter in drawn:
                CrewMember.objects.create_with_user(
                    user=user,
                    owner_id=lst.owner_id,
                    crew=crew,
                    list_fighter=fighter,
                    source=CrewMember.DRAWN,
                )

    crew.status = Crew.LOCKED
    crew.save_with_user(user=user)

    if whole_gang:
        outcome = f"{chosen_count} fighters (whole gang)"
    else:
        outcome_parts = [f"{chosen_count} chosen"]
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
        # Description is a neutral headline; the concrete counts (and any skips
        # or roll detail) live in `outcome`, so the two can never disagree.
        description=f"Crew selected for {lst.name}",
        outcome=outcome,
    )

    return CrewLockResult(
        crew=crew,
        chosen_count=chosen_count,
        random_count=len(drawn),
        roll_detail=roll_detail,
        campaign_action=campaign_action,
        whole_gang=whole_gang,
        skipped_ineligible=skipped_ineligible,
    )
