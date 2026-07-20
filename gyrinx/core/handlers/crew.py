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
from django.db.models import Q
from django.utils import timezone

from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.crew import Crew, CrewMember, roll_selection_spec
from gyrinx.core.models.list import ListFighter
from gyrinx.models import FighterCategoryChoices
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)

# Categories a fighter must be opted into to appear in a crew: hangers-on don't
# normally take part in a battle (rulebook — only forced in on home turf), and
# vehicle crew are an Ash-Wastes thing. Everything else (including Brutes, which
# "are treated like any other fighter when selecting a crew") is eligible.
DEFAULT_EXCLUDED_CREW_CATEGORIES = frozenset(
    {FighterCategoryChoices.HANGER_ON.value, FighterCategoryChoices.CREW.value}
)


def eligible_crew_fighters(lst, *, included=()):
    """Fighters in ``lst`` eligible to be picked or drawn for a crew.

    Active state, not the stash, not archived — mirrors the single-fighter
    add-injury eligibility and the original crew-template work (#1360).
    Scenario-specific restrictions (no Leader, one Champion, …) are surfaced
    as warnings later, not enforced here.

    Vehicles and exotic beasts are excluded: they are bought as wargear and
    deploy alongside the fighter that owns them (rulebook p86), so they are
    never selected in their own right. ``source_assignment__isnull=True`` drops
    them — a child fighter is one spawned by an owner's equipment assignment.
    They still join the crew, enrolled against their owner by
    :func:`sync_linked_crew_members`.

    Hangers-on and vehicle crew are excluded too, unless their category is in
    ``included`` (a per-crew opt-in — the player's choice, e.g. an Ash-Wastes
    game where crew field, or a home-turf scenario that drags hangers-on in).
    The check is on the fighter's *effective* category, so a promotion's
    ``category_override`` wins over the content fighter's own category.
    """
    excluded = DEFAULT_EXCLUDED_CREW_CATEGORIES - set(included)
    qs = ListFighter.objects.filter(
        list=lst,
        archived=False,
        content_fighter__is_stash=False,
        injury_state=ListFighter.ACTIVE,
        source_assignment__isnull=True,
    )
    if excluded:
        qs = qs.exclude(
            Q(category_override__in=excluded)
            | Q(
                category_override__isnull=True,
                content_fighter__category__in=excluded,
            )
        )
    return qs


def eligible_crew_fighters_for_loadouts(lst, *, included=()):
    """The eligible fighters, loaded for loadout work.

    ``with_related_data()`` brings each fighter's equipment sets *and* their
    assignments in with the batch, which is what lets the resolver and the
    set-scoped cost run without a query per fighter.
    """
    return eligible_crew_fighters(lst, included=included).with_related_data()


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

    Each fighter's vehicles and exotic beasts are forecast alongside them (they
    deploy with their owner), so the total matches what the lock will enrol.
    """
    rows = []
    total = 0
    roster = list(
        eligible_crew_fighters_for_loadouts(
            crew.list, included=crew.included_categories
        )
    )
    for fighter in roster:
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

    # Vehicles/exotic beasts owned by the roster ride in too (see
    # sync_linked_crew_members); they are not in the eligible pool, so add them
    # here or the forecast would understate the crew by their cost.
    children = (
        ListFighter.objects.filter(
            source_assignment__list_fighter__in=roster,
            archived=False,
            injury_state=ListFighter.ACTIVE,
        )
        .with_related_data()
        .distinct()
    )
    for child in children:
        rating = child.cost_int_for_equipment_set(None)
        total += rating
        rows.append(
            {
                "fighter_id": child.pk,
                "name": child.name,
                "category": child.content_fighter.get_category_display(),
                "loadout": None,
                "rating": rating,
            }
        )
    return {"rows": rows, "total": total}


def crew_spread_rating(crew: Crew) -> tuple[Optional[int], bool]:
    """What a crew is worth *right now* for spread/underdog comparison, and
    whether that figure is provisional. Returns ``(rating, is_provisional)``.

    The single definition of a crew's comparison rating, so the battle page and
    the (future) crew-page spread can never drift — two copies of this cascade
    is how they would. Three cases:

    - a **pending random draw** has no known rating yet — ``(None, False)``; the
      side drops out of the comparison until it is drawn;
    - a **whole-gang draft** that has enrolled nobody would otherwise read 0¢
      ("no fighters") rather than "the whole gang attends", so it is forecast
      from the currently-eligible roster — ``(forecast total, True)``,
      provisional because the roster only resolves at battle start;
    - **otherwise** the crew's own :meth:`Crew.rating` — live until the battle
      freezes ``rating_played``, the played snapshot after — ``(rating, False)``.

    Reads ``crew.members`` from a caller's ``prefetch_related("members")`` cache
    when present, so it adds no query in the whole-gang / locked cases; the
    forecast branch runs one batched roster load via
    :func:`crew_whole_gang_projection`.
    """
    if crew.pending_roll:
        return None, False
    if not crew.is_locked and crew.is_whole_gang and not crew.members.exists():
        return crew_whole_gang_projection(crew)["total"], True
    return crew.rating(), False


def crew_battle_spread(crew: Crew) -> Optional[int]:
    """How far ``crew``'s rating sits below the highest crew in its battle, in
    credits — or ``None`` when there's nothing to say.

    The crew page needs the *other* crews' ratings, which the page itself
    doesn't load. This loads the battle's live (non-archived) crews once — with
    members prefetched — and asks each for its comparison rating via
    :func:`crew_spread_rating`. Every per-crew rating goes through the batched
    :meth:`ListFighter.with_related_data` load, so the opponent cost is constant
    in the number of fighters, not a query per opposing fighter.

    Returns the positive gap below the top crew, or ``None`` when it can't be
    computed (fewer than two crews have a known rating), this crew has no rating
    yet (its draw is pending), or this crew *is* the top (nothing below).
    """
    crews = list(
        crew.battle.crews.filter(archived=False)
        .select_related("list")
        .prefetch_related("members")
    )
    ratings = {other.id: crew_spread_rating(other)[0] for other in crews}
    known = [r for r in ratings.values() if r is not None]
    this = ratings.get(crew.id)
    if len(known) < 2 or this is None:
        return None
    gap = max(known) - this
    return gap or None


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


@traced("sync_linked_crew_members")
def sync_linked_crew_members(*, user, crew: Crew) -> None:
    """Enrol every crew member's vehicles and exotic beasts, and drop any whose
    owner is no longer on the crew.

    A vehicle or exotic beast is bought as wargear and deploys alongside the
    fighter that owns it (rulebook p86) — it is never selected in its own right,
    so it is kept out of the selection form and the random pool (see
    :func:`eligible_crew_fighters`). Instead it rides in here as a ``LINKED``
    member whenever its owner is a member, which is what makes it count towards
    the crew's rating, show on the sheet, and print.

    Idempotent: reconciles the ``LINKED`` rows against the children of the
    crew's own (non-linked) members each time, so it is safe to call after any
    change to who is in the crew.
    """
    owner_ids = list(
        crew.members.exclude(source=CrewMember.LINKED).values_list(
            "list_fighter_id", flat=True
        )
    )
    # A downed or archived beast doesn't deploy — mirror the fighter eligibility
    # rules rather than dragging a dead beast onto the table.
    wanted = set(
        ListFighter.objects.filter(
            source_assignment__list_fighter_id__in=owner_ids,
            archived=False,
            injury_state=ListFighter.ACTIVE,
        ).values_list("id", flat=True)
    )
    linked = {
        m.list_fighter_id: m for m in crew.members.filter(source=CrewMember.LINKED)
    }
    stale = [m.pk for fighter_id, m in linked.items() if fighter_id not in wanted]
    if stale:
        crew.members.filter(pk__in=stale).delete_with_user(user=user)

    # Never add a fighter already on the crew a second time (unique(crew, list_fighter)).
    present = set(crew.members.values_list("list_fighter_id", flat=True))
    for child_id in wanted - present:
        CrewMember.objects.create_with_user(
            user=user,
            owner_id=crew.list.owner_id,
            crew=crew,
            list_fighter_id=child_id,
            source=CrewMember.LINKED,
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
    equipment_sets=None,
    included_categories=None,
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

    ``included_categories`` records the normally-excluded categories (hangers-on
    / vehicle crew) this crew opts in — persisted so the random draw, whole-gang
    enrolment, and lock re-check at battle start all match what was offered.
    ``None`` leaves it unchanged.
    """
    crew.selection_method = method
    crew.custom_count = custom_count if method in (Crew.CUSTOM, Crew.HYBRID) else None
    crew.random_spec = random_spec if method in (Crew.RANDOM, Crew.HYBRID) else ""
    if included_categories is not None:
        crew.included_categories = list(included_categories)
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
        crew.members.filter(pk__in=stale).delete_with_user(user=user)

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

    # Any chosen fighter that owns a vehicle/beast brings it along; drop the
    # linked rows of anyone just removed.
    sync_linked_crew_members(user=user, crew=crew)

    return crew


@traced("handle_crew_archive")
@transaction.atomic
def handle_crew_archive(*, user, crew: Crew) -> CampaignAction:
    """Archive a crew and log it.

    Archiving withdraws the crew from the battle — it drops out of the
    participants table, the crew print filter, and the played-rating snapshot at
    battle end — but is kept as a record (its detail page still renders). Like
    everything else here it never touches the gang's canonical cost, credits, or
    audit stream; the one thing written beyond the crew is a battle-linked
    CampaignAction so the campaign log shows the withdrawal happened.

    Only the crew row is archived, not its members or extras: the (battle, list)
    unique constraint is conditional on ``archived=False``, so archiving the crew
    is all it takes to free the gang for a fresh crew on the same battle.
    """
    # Lock the crew row so two concurrent archive POSTs serialise: the loser
    # sees archived=True and raises instead of logging a duplicate withdrawal.
    # Same pattern as handle_crew_lock / handle_battle_end.
    crew = (
        Crew.objects.select_for_update()
        .select_related("battle", "list")
        .get(pk=crew.pk)
    )
    if crew.archived:
        raise ValidationError("This crew has already been archived.")
    gang = crew.list
    crew.archived = True
    crew.archived_at = timezone.now()
    crew.save_with_user(user=user)

    # Battle.campaign is a non-nullable FK, so there is always a campaign to log.
    # A neutral headline with no outcome, matching handle_crew_lock: there is
    # nothing for the description to contradict.
    return CampaignAction.objects.create(
        user=user,
        owner=user,
        campaign=crew.battle.campaign,
        list=gang,
        battle=crew.battle,
        description=f"Crew archived for {gang.name}",
    )


@traced("snapshot_crew_rating")
def snapshot_crew_rating(
    *, user, crew: Crew, field: str, also_field: str = None
) -> int:
    """Freeze the crew's live rating, and each member's share of it, into
    ``field`` (``"rating_selected"`` or ``"rating_played"``).

    Both snapshots are taken the same way, from the same live computation, at
    two different moments — the lock records what was *picked*, the end of the
    battle records what actually *fought*. One implementation so the two can
    never be computed differently.

    ``also_field`` writes the *same* frozen figure to a second field in the same
    pass. It exists for the record-after-the-fact case: a crew confirmed on an
    already-ended battle freezes ``rating_selected`` and ``rating_played`` at
    once (there was no gap between picking and fielding), and doing it in one
    pass keeps it to a single member write rather than two history rows.

    Sets the field(s) on the ``crew`` instance (the caller saves it, alongside
    whatever else it is changing) and persists them on each member.
    """
    fields = [field] + ([also_field] if also_field else [])
    ratings = crew.live_member_ratings()
    for member in crew.members.all():
        share = ratings.get(member.id, 0)
        for f in fields:
            setattr(member, f, share)
        member.save_with_user(user=user)
    total = sum(ratings.values())
    for f in fields:
        setattr(crew, f, total)
    return total


@traced("snapshot_played_crew_ratings")
def snapshot_played_crew_ratings(*, user, battle) -> int:
    """Freeze what each of ``battle``'s crews fielded, at the moment it ended.

    Only locked, non-archived crews are snapshotted: a crew that was never
    confirmed didn't field anything, and an archived crew was withdrawn before
    the battle, so neither has a fact to freeze and inventing one would claim a
    battle it never fought. Returns how many crews were frozen.
    """
    crews = list(battle.crews.filter(archived=False).prefetch_related("members"))
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

    eligible = eligible_crew_fighters(lst, included=crew.included_categories)
    eligible_ids = set(eligible.values_list("pk", flat=True))
    members = list(crew.members.all())

    # Whole gang: Custom Selection with no number in brackets and nobody named.
    # Judged before the eligibility sweep below — picks that have all since
    # become ineligible make an empty custom crew, not a whole-gang one.
    whole_gang = crew.is_whole_gang and not members

    # Re-check eligibility at lock time: a fighter chosen while the recipe was
    # being built may since have been archived, stashed, killed, or put in
    # recovery. The rulebook excludes fighters who can't take part from every
    # selection method, so drop them here rather than enrolling them. Linked
    # vehicles/beasts are exempt — they aren't in the eligible pool by design,
    # and sync_linked_crew_members below drops any whose owner was just cut.
    stale = [
        m.pk
        for m in members
        if m.source != CrewMember.LINKED and m.list_fighter_id not in eligible_ids
    ]
    skipped_ineligible = len(stale)
    if stale:
        crew.members.filter(pk__in=stale).delete_with_user(user=user)

    if whole_gang or crew.loadout_overrides:
        # Loaded once, with each fighter's sets, so resolving the whole roster's
        # loadouts costs no query per fighter.
        roster = list(
            eligible_crew_fighters_for_loadouts(lst, included=crew.included_categories)
        )
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

    # Linked vehicles/beasts aren't "chosen" — they ride in with their owner, so
    # they don't count towards the selected-fighter tally in the campaign log.
    chosen_count = crew.members.exclude(source=CrewMember.LINKED).count()

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

    # Bring in each attending fighter's vehicles/exotic beasts before the
    # snapshot, so what they contribute is frozen into the crew's rating too.
    sync_linked_crew_members(user=user, crew=crew)

    crew.status = Crew.LOCKED
    # Record what was picked. The crew goes on reporting its live rating until
    # the battle ends — this is the note-worthy "was X when you picked it"
    # figure, not the headline one (see Crew.rating).
    if crew.battle.has_ended():
        # Recorded after the fact: players settled the crew at the table, the
        # battle is already over, and they are only now logging it. There is no
        # future battle-end to freeze what fought, so the lock is that moment —
        # freeze rating_played here too, equal to rating_selected (nothing
        # happened between picking and fielding to move them apart).
        snapshot_crew_rating(
            user=user, crew=crew, field="rating_selected", also_field="rating_played"
        )
    else:
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
