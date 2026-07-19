"""Handlers for battle crews (#1346).

Two pieces of real business logic live here:

- **Saving a recipe** — applying a selection method to a crew, which means
  clearing whatever belongs to the *other* methods and reconciling the chosen
  :class:`CrewMember` rows with the player's picks.
- **Locking a crew** — at battle start we roll the random-selection spec once,
  draw that many fighters (and a card each) from the eligible pool, add them as
  members, record the rating they were picked at, and write a battle-linked
  campaign action. There are no re-rolls after this, and a locked crew is not
  editable.
- **Freezing what fought** — when the battle ends, each locked crew's rating is
  snapshotted again. Until then a crew reports its live rating, because that is
  what the gang would actually field; afterwards the record must stop moving.

Simple CRUD (extras) stays in the views.
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


def eligible_crew_fighters_for_loadouts(lst):
    """The eligible fighters, loaded for loadout work.

    ``with_related_data()`` brings each fighter's equipment sets *and* their
    assignments in with the batch, which is what lets the resolver and the
    set-scoped cost run without a query per fighter.
    """
    return eligible_crew_fighters(lst).with_related_data()


@traced("crew_whole_gang_projection")
def crew_whole_gang_projection(crew: Crew):
    """What locking a whole-gang crew would enrol, as it stands right now.

    One row per currently-eligible fighter — the equipment set they would bring
    (resolved by :meth:`Crew.resolve_loadout`, the same call the lock makes) and
    what they would cost under it — plus the total.

    This is a **forecast, not a promise**: the roster resolves at battle start,
    so a fighter recruited or lost in the meantime legitimately changes it. The
    total is display-only and is deliberately not ``Crew.rating()``, which stays
    live-for-drafts / snapshot-once-locked.
    """
    rows = []
    total = 0
    for fighter in eligible_crew_fighters_for_loadouts(crew.list):
        equipment_set = crew.resolve_loadout(fighter)
        rating = fighter.cost_int_for_equipment_set(equipment_set)
        total += rating
        rows.append(
            {
                "fighter_id": fighter.pk,
                "name": fighter.name,
                "category": fighter.content_fighter.get_category_display(),
                "loadout": equipment_set.name if equipment_set else None,
                "rating": rating,
            }
        )
    return {"rows": rows, "total": total}


def crew_loadout_gang_fighters(lst):
    """Every fighter in the gang, loaded with their equipment sets.

    Deliberately wider than :func:`eligible_crew_fighters`: this is the roster a
    *stored* loadout choice is validated against, and ineligibility is usually
    temporary. A fighter in recovery today may well be back by battle start, so
    their choice still means something even though no form would offer it.
    """
    return ListFighter.objects.filter(list=lst).with_related_data()


@traced("handle_crew_loadouts_save")
@transaction.atomic
def handle_crew_loadouts_save(*, user, crew: Crew, choices) -> Crew:
    """Record which equipment set each fighter should bring at lock.

    ``choices`` maps a fighter id to the set they should bring, with ``None``
    meaning an explicit choice of the Default card — stored as such, so it
    sticks even if the fighter's own active set changes afterwards.

    Merged into what is already stored, not rebuilt from the choices. The form
    only lists *currently eligible* fighters, so rebuilding would delete the
    choice made for anyone who happens to be in recovery when someone else
    re-saves the page — and if they recover before the lock they would then turn
    up on their default kit, silently discarding a decision the player made.
    Entries the form didn't ask about are kept as long as they still resolve;
    only genuinely meaningless ones (a deleted set, a set belonging to someone
    else, a fighter no longer in the gang) are pruned.
    """
    merged = crew.pruned_loadout_overrides(crew_loadout_gang_fighters(crew.list))
    merged.update(
        {
            str(fighter_id): {
                Crew.LOADOUT_SET_KEY: (
                    str(chosen_set.pk) if chosen_set is not None else None
                )
            }
            for fighter_id, chosen_set in (choices or {}).items()
        }
    )
    crew.loadout_overrides = merged
    crew.save_with_user(user=user)
    return crew


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
    equipment_sets=None,
) -> Crew:
    """Save a crew's selection recipe under ``method``.

    Each method uses a different subset of the recipe, so the fields belonging
    to the other methods are cleared: switching Hybrid → Random nulls
    ``custom_count`` and drops the chosen members, switching → Custom blanks
    ``random_spec``. That is what keeps a contradictory recipe (an entirely
    random selection that also names fighters) unrepresentable.

    The crew's chosen :class:`CrewMember` rows are then reconciled with
    ``chosen_fighters``: members exist from selection time, not just after the
    lock. ``equipment_sets`` maps a chosen fighter's id to the equipment set
    they bring (``None`` = the Default card) — Custom Selection lets the player
    choose that, so it is part of the recipe. Drawn members are never touched
    here — only a draft crew is editable, and a draft has none.
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

    sets = equipment_sets or {}

    def set_id_for(fighter_id):
        chosen_set = sets.get(fighter_id)
        return chosen_set.pk if chosen_set is not None else None

    chosen = {
        m.list_fighter_id: m for m in crew.members.filter(source=CrewMember.CHOSEN)
    }
    stale = [m.pk for fighter_id, m in chosen.items() if fighter_id not in wanted]
    if stale:
        crew.members.filter(pk__in=stale).delete()

    # A fighter who stays on the crew may have been switched to a different card.
    for fighter_id, member in chosen.items():
        if fighter_id not in wanted:
            continue
        set_id = set_id_for(fighter_id)
        if member.equipment_set_id != set_id:
            member.equipment_set_id = set_id
            member.save_with_user(user=user)

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
            equipment_set_id=set_id_for(fighter_id),
        )

    return crew


@traced("snapshot_crew_rating")
def snapshot_crew_rating(*, user, crew: Crew, field: str) -> int:
    """Freeze the crew's live rating, and each member's share of it, into
    ``field`` (``"rating_selected"`` or ``"rating_played"``).

    Both snapshots are taken the same way, from the same live computation, at
    two different moments — the lock records what was *picked*, the end of the
    battle records what actually *fought*. One implementation so the two can
    never be computed differently.

    Sets the field on the ``crew`` instance (the caller saves it, alongside
    whatever else it is changing) and persists it on each member.
    """
    ratings = crew.live_member_ratings()
    for member in crew.members.all():
        setattr(member, field, ratings.get(member.id, 0))
        member.save_with_user(user=user)
    total = sum(ratings.values())
    setattr(crew, field, total)
    return total


@traced("snapshot_played_crew_ratings")
def snapshot_played_crew_ratings(*, user, battle) -> int:
    """Freeze what each of ``battle``'s crews fielded, at the moment it ended.

    Only locked crews are snapshotted: a crew that was never confirmed didn't
    field anything, so there is no fact to freeze and inventing one would claim
    a battle it never fought. Returns how many crews were frozen.
    """
    crews = list(battle.crews.prefetch_related("members"))
    frozen = 0
    for crew in crews:
        if not crew.is_locked:
            continue
        snapshot_crew_rating(user=user, crew=crew, field="rating_played")
        crew.save_with_user(user=user)
        frozen += 1
    return frozen


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

    if whole_gang or crew.loadout_overrides:
        # Loaded once, with each fighter's sets, so resolving the whole roster's
        # loadouts costs no query per fighter.
        roster = list(eligible_crew_fighters_for_loadouts(lst))
        # Self-heal the advisory map while we have the roster in hand: entries
        # for fighters who are no longer eligible, or for sets that have since
        # been deleted, are dropped. Persisted by the save below.
        crew.loadout_overrides = crew.pruned_loadout_overrides(roster)

        if whole_gang:
            # Nobody was asked at selection time which card each model brings,
            # so each one brings what the pre-lock forecast showed: the loadout
            # chosen for this battle, or failing that the set they are already
            # using on their fighter card (None = Default).
            for fighter in roster:
                equipment_set = crew.resolve_loadout(fighter)
                CrewMember.objects.create_with_user(
                    user=user,
                    owner_id=lst.owner_id,
                    crew=crew,
                    list_fighter=fighter,
                    source=CrewMember.CHOSEN,
                    equipment_set_id=equipment_set.pk if equipment_set else None,
                )

    chosen_count = crew.members.count()

    random_count, roll_detail = (0, "")
    drawn = []
    drawn_cards = []
    if crew.selection_method in (Crew.RANDOM, Crew.HYBRID):
        random_count, roll_detail = roll_selection_spec(crew.random_spec, rng=rng)
        if random_count > 0:
            # Exclude everyone already on the crew, not just the chosen ones:
            # re-drawing a present fighter would trip unique(crew, list_fighter).
            present_ids = set(crew.members.values_list("list_fighter_id", flat=True))
            pool = list(
                eligible.exclude(pk__in=present_ids).prefetch_related("equipment_sets")
            )
            rng.shuffle(pool)
            drawn = pool[:random_count]
            for fighter in drawn:
                # A fighter drawn at random brings a randomly determined card
                # too — the rulebook's deck holds one card per model, chosen at
                # random when the model has several. None is the Default card.
                cards = [None] + list(fighter.equipment_sets.all())
                equipment_set = rng.choice(cards)
                CrewMember.objects.create_with_user(
                    user=user,
                    owner_id=lst.owner_id,
                    crew=crew,
                    list_fighter=fighter,
                    source=CrewMember.DRAWN,
                    equipment_set=equipment_set,
                )
                drawn_cards.append(
                    f"{fighter.name} ({equipment_set.name if equipment_set else 'Default'})"
                )

    crew.status = Crew.LOCKED
    # Record what was picked. The crew goes on reporting its live rating until
    # the battle ends — this is the note-worthy "was X when you picked it"
    # figure, not the headline one (see Crew.rating).
    snapshot_crew_rating(user=user, crew=crew, field="rating_selected")
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
        # Name what the draw produced, with each drawn model's card, so the
        # result is auditable after the fact.
        if drawn_cards:
            outcome += " — " + ", ".join(drawn_cards)

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
