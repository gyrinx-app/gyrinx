"""Build player-facing gang and campaign history from ledger events.

Return plain ``Act`` dataclasses for views to filter, group and render.
Events from one operation share a batch. Group related edits into one
history line, and nest grants or cascading removals beneath their source.

Translate removal assignments into the change the player saw: archiving
an assignment that removes Mounted restores Mounted. Hide internal
carriers and fold a weapon's included profiles into its weapon line.
"""

from dataclasses import dataclass, field

from django.urls import reverse

from n26.core.campaigns import ARCHIVED_COUNTER_NOTE_PREFIX, NO_CEILING
from n26.core.cloning import CLONED_RATING_NOTE_PREFIX, clone_event_details
from n26.core.effects import kind_of
from n26.core.models import Assignment, CampaignEvent, LedgerEvent, Reason
from n26.core.models.activity import read_note
from n26.core.operations import CLEAN_HOUSE

Kind = LedgerEvent.Kind

#: The kinds that concern credits. "Amended" is here because re-choosing
#: how a thing is built can change what it charges.
CREDITS = {
    Kind.PURCHASED,
    Kind.REFUNDED,
    Kind.SOLD,
    Kind.REPRICED,
    Kind.AMENDED,
    Kind.TRANSFERRED,
    Kind.INCOME,
    Kind.CREDITS_ADJUSTED,
}

#: The kinds that are a campaign's asset coming to the gang or leaving
#: it. Nothing else is ever written with them, so a record of either kind
#: is a holding's whether or not the asset still stands.
HOLDING = {Kind.GAINED, Kind.LOST}

#: The kinds that are always about the model itself rather than its kit.
PERSONAL = {
    Kind.TOOK_AWAY,
    Kind.RENAMED,
    Kind.NOTED,
    Kind.LORE_EDITED,
    Kind.IMAGE_SET,
    Kind.IMAGE_CLEARED,
    Kind.STAT_SET,
    Kind.STAT_CLEARED,
    Kind.RATING_SET,
    Kind.RATING_RESET,
}


@dataclass(frozen=True)
class Span:
    """One stretch of a sentence, linked if ``href`` says where to."""

    text: str
    href: str = ""


@dataclass(frozen=True)
class Sub:
    """A related acquisition, removal or movement nested beneath a history entry."""

    name: str
    kind: str = ""
    note: str = ""

    @property
    def detail(self):
        """Combine the non-empty kind and note after the nested entry's name."""
        return ", ".join(part for part in (self.kind, self.note) if part)


@dataclass
class Act:
    """A history entry with display text, balance movements and filter identities.

    Negative credits or Trade Points represent spending; positive values
    represent returns. ``actor`` is the sentence's subject, or empty when
    no person is named. ``category`` and model identities support filtering;
    ``search`` combines searchable text.
    """

    when: object
    actor: str
    spans: tuple[Span, ...]
    credits: int = 0
    trade_points: int = 0
    rating: int = 0
    note: str = ""
    #: Actor whose profile and badge accompany the name. None for unnamed
    #: actors and for the viewer, whose display name is You.
    actor_user: object | None = None
    subs: list[Sub] = field(default_factory=list)
    category: str = "kit"
    miniature_pk: str = ""
    miniature_name: str = ""
    #: Gang identity for entries displayed alongside other gangs. Empty in
    #: a single gang's history.
    gang_pk: str = ""
    gang_name: str = ""
    #: Filter identity for ownership acts, whose sentence omits the actor.
    actor_pk: int | None = None
    #: A transfer concerns both gangs even though it draws no gang subtitle.
    related_gang_pks: tuple[str, ...] = ()

    @property
    def search(self):
        # Spans carry their own spacing — joined with nothing, so a
        # phrase that crosses a span boundary still matches.
        told = "".join(span.text for span in self.spans)
        words = [told, *(sub.name for sub in self.subs), self.note]
        return " ".join(words).casefold()


#: How many events back a snapshot reads. Acts are made of events — one
#: hire is a dozen of them — so a window counted in acts is not something
#: a query can ask for, and this is many times the handful of acts any
#: snapshot wants.
SNAPSHOT_WINDOW = 200

_COUNTER_MACHINERY = {Kind.COUNTER_OPENED, Kind.COUNTER_CHECKPOINTED}


def build(gang, viewer=None):
    """Return this gang's complete history, oldest first.

    Use You for the viewer's actions and names for other actors. Batch all
    related reads so query count does not grow per event.
    """
    return _acts_from(_events(gang), viewer, alive=_alive(gang))


def latest(gang, limit=5, viewer=None):
    """Return the gang's most recent entries, newest first.

    Read a bounded event window larger than the requested entry count because
    one operation may contain many events. Take entries from its recent end
    to avoid incomplete older groups. Omit model links to avoid a roster lookup.

    Load events and their referenced assignments. Additional conditional reads
    resolve propagated grant sources, roll slots and referenced rolls outside
    the event window.
    """
    acts = _acts_from(_events(gang, window=SNAPSHOT_WINDOW), viewer, alive=frozenset())
    return list(reversed(acts))[:limit]


def _events(gang, window=None):
    """The gang's events, oldest first — all of them, or the last
    ``window`` of them read back to front and turned round."""
    rows = (
        gang.ledger_events.exclude(kind__in=_COUNTER_MACHINERY)
        .exclude(kind=Kind.RATING_SET, note__startswith=CLONED_RATING_NOTE_PREFIX)
        .select_related(
            "miniature",
            "actor",
            "action_record__fighter",
            "post_battle_revision",
            "campaign",
            "campaign_asset__asset__asset_type",
            "counterpart",
            "battle",
        )
    )
    if window is None:
        return list(rows.order_by("created", "id"))
    newest = list(rows.order_by("-created", "-id")[:window])
    newest.reverse()
    return newest


def _alive(gang):
    """The models still on the roster. The history keeps the dead, but
    only the living have a page to link to — a departed model's name
    reads as words."""
    from n26.core.models import Miniature

    return set(
        Miniature.objects.filter(
            membership__gang=gang, membership__archived=False
        ).values_list("pk", flat=True)
    )


def _acts_from(events, viewer, *, alive):
    """The acts these events tell, oldest first."""
    rows = _rows_for(events)
    _name_the_rolls(events, rows)
    _name_the_named_picks(events, rows)
    sources = _comes_with_sources(events, rows)
    acts = []
    #: Where each thing's opening act landed, so an old record's grant
    #: can fold under it rather than stand beside it.
    act_of = {}
    for cluster in _clusters(events):
        _tell_cluster(cluster, rows, acts, act_of, viewer, alive, sources)
    return acts


def _comes_with_sources(events, rows):
    """Load current source names for materialised catch-up grants in one query.

    Skip the query when no such grants occur in the supplied events.
    """
    carrier_ids = {
        rows[e.assignment_id].materialised_for_id
        for e in events
        if e.kind == Kind.CAUGHT_UP
        and e.assignment_id in rows
        and rows[e.assignment_id].materialised_for_id is not None
    }
    if not carrier_ids:
        return {}
    carriers = Assignment.with_assignables(
        Assignment.objects.filter(pk__in=carrier_ids)
    )
    return {carrier.pk: str(carrier.assignable) for carrier in carriers}


def _rows_for(events):
    """The assignments the events name, resolved to their things."""
    wanted = {e.assignment_id for e in events if e.assignment_id}
    wanted |= {_named_pick_id(e) for e in events} - {None}
    fetched = Assignment.with_assignables(
        Assignment.objects.filter(pk__in=wanted).select_related(
            "ledger_entry",
            "miniature",
            "miniature_root",
            "stash",
            # A pick says its kind through the question it answered.
            "chosen_for_slot__slot_type",
            # A pick of a hidden slot is not told; the slot is read off
            # the pick, or off the assignment it was chosen for.
            "chosen_for__slot",
        )
    )
    return {row.pk: row for row in fetched}


def _named_pick_id(e):
    """The pick a label's removal or restoration names, or None.

    Archiving a label removes each gang's copy of it with its pick as
    ``before_pick``; unarchiving puts it back with that pick as
    ``after_pick``. Every other removal that names a pick names the
    removed pick itself, so it says nothing more.
    """
    if e.kind == Kind.REMOVED:
        pick = e.before_pick_id
    elif e.kind == Kind.RESTORED:
        pick = e.after_pick_id
    else:
        return None
    return pick if pick is not None and pick != e.assignment_id else None


def _name_the_named_picks(events, rows):
    """Put the pick on each label removed or restored with one, so the
    sentence can say what it was. The picks come in with the records'
    own read (``_rows_for``), so this costs nothing further."""
    for e in events:
        pick = rows.get(_named_pick_id(e))
        if pick is not None and pick.chosen_for_id == e.assignment_id:
            e.named_pick = pick


def _stood_at(e):
    """What an archived counter or label stood at as it went or came back:
    " (was 4)" and " (was Lawful)" on a removal, " (4)" and " (Lawful)"
    on a restoration. Nothing for any other event."""
    if e.note.startswith(ARCHIVED_COUNTER_NOTE_PREFIX):
        value = e.note.removeprefix(ARCHIVED_COUNTER_NOTE_PREFIX)
    elif getattr(e, "named_pick", None) is not None:
        value = _name(e.named_pick)
    else:
        return ()
    return (Span(f" (was {value})" if e.kind == Kind.REMOVED else f" ({value})"),)


def _name_the_rolls(events, rows):
    """Load slots for roll events and recorded rolls for selections.

    Use separate conditional reads because most history events involve no roll.
    """
    from n26.library.models import Slot

    rolled = [e for e in events if e.kind == Kind.ROLLED]
    picks = [row for row in rows.values() if row.roll_id is not None]
    if not rolled and not picks:
        return
    slots = Slot.objects.in_bulk({e.slot_id for e in rolled if e.slot_id})
    for e in rolled:
        e.slot = slots.get(e.slot_id)
    by_pk = {e.pk: e for e in rolled}
    missing = {row.roll_id for row in picks} - set(by_pk)
    if missing:
        by_pk |= LedgerEvent.objects.in_bulk(missing)
    for row in picks:
        row.roll = by_pk.get(row.roll_id)


def _clusters(events):
    """Group adjacent events with the same batch; leave unbatched events separate."""
    grouped = []
    for e in events:
        if grouped and e.batch is not None and grouped[-1][0].batch == e.batch:
            grouped[-1].append(e)
        else:
            grouped.append([e])
    return grouped


def _tell_cluster(cluster, rows, acts, act_of, viewer, alive, sources):
    """Build entries for one batch, nesting dependent events beneath their sources.

    Build source entries before attaching grants and cascading removals,
    refunds or sales. A dependent event remains separate if its source has
    no entry. Unbatched grants may attach by cause to an earlier source entry;
    batched cause-based grants stay within their batch. A pick may instead
    attach to a loaded roll entry from another batch on the same day.
    """
    # Each clone writes its openings before its standalone event. Group by
    # that boundary so companions stay included and later moves of copied
    # kit cannot change which clone's totals the history recovers.
    clone_totals = {}
    clone_credits = clone_rating = 0
    for event in cluster:
        if event.kind != Kind.CLONED:
            continue
        if event.assignment_id is not None:
            clone_credits += event.credits_delta
            clone_rating += event.rating_delta
        else:
            clone_totals[event.pk] = (clone_credits, clone_rating)
            clone_credits = clone_rating = 0
    here = {e.assignment_id for e in cluster if e.assignment_id is not None}
    # Nest campaign type grants and their built-ins under the joining
    # event. Nest their removals under the departure event.
    joined = any(e.kind == Kind.JOINED_CAMPAIGN for e in cluster)
    left = any(e.kind == Kind.LEFT_CAMPAIGN for e in cluster)
    # A label removed or restored with its pick says the pick: "removed
    # Alignment (was Lawful)". The pick's own event would say it again.
    told_picks = {
        e.named_pick.pk for e in cluster if getattr(e, "named_pick", None) is not None
    }
    standing = []
    waiting = []
    for e in cluster:
        row = rows.get(e.assignment_id)
        if _machinery(e, row):
            continue
        if e.kind in {Kind.REMOVED, Kind.RESTORED} and e.assignment_id in told_picks:
            continue
        if (
            e.kind == Kind.GRANTED
            and row is not None
            and _roll_key(row.roll_id) in act_of
        ):
            # A pick made for a roll folds under the roll: "rolled 24"
            # with "Out Cold" beneath it is one act however many
            # requests it took. The roll's act is keyed apart from the
            # records', so a pick whose roll is outside the window can
            # never fold under some record's act instead. Same day only —
            # a pick made days after its roll is its own act on its own
            # day, and says which roll it came from in its own sentence.
            home = act_of[_roll_key(row.roll_id)]
            if home.when.date() == e.created.date():
                home.subs.append(Sub(name=_name(row), kind=_kindword(row)))
                act_of.setdefault(row.pk, home)
                continue
        ride = _rides(e, row)
        if (
            ride is None
            and e.kind in {Kind.GRANTED, Kind.REMOVED}
            and row is not None
            and row.campaign_type_id is not None
        ):
            # Suppress campaign carrier events when their join or departure lies
            # outside the loaded window; their internal type has no standalone label.
            if e.kind == Kind.GRANTED and joined:
                waiting.append((e, row, _THE_JOINING))
            elif e.kind == Kind.REMOVED and left:
                waiting.append((e, row, _THE_LEAVING))
            continue
        if ride is not None:
            if ride in here:
                waiting.append((e, row, ride))
                continue
            if e.kind == Kind.GRANTED and e.batch is None:
                home = act_of.get(ride)
                if home is not None:
                    home.subs.append(Sub(name=_name(row), kind=_kindword(row)))
                    act_of.setdefault(row.pk, home)
                    continue
        standing.append((e, row))

    #: Map records to this batch's entries so dependants attach to the
    #: current change rather than an earlier acquisition.
    local = {}
    caught_up = [(e, row) for e, row in standing if e.kind == Kind.CAUGHT_UP]
    if caught_up:
        standing = [(e, row) for e, row in standing if e.kind != Kind.CAUGHT_UP]
        for act, group in _caught_up_acts(caught_up, sources, alive):
            acts.append(act)
            for _, row in group:
                if row is not None:
                    local[row.pk] = act
                    act_of.setdefault(row.pk, act)
    if _is_clean_house(standing):
        acts.append(_clean_house_as_one(standing, viewer, alive))
    elif _one_edit_of_what_a_model_is(standing):
        act = _edits_as_one(standing, viewer, alive)
        acts.append(act)
        for _, row in standing:
            if row is not None:
                local[row.pk] = act
                act_of.setdefault(row.pk, act)
    else:
        for e, row in standing:
            act = _one_act(e, row, viewer, alive)
            if e.kind == Kind.CLONED and e.miniature_id is not None:
                _, credits, rating = clone_event_details(e.note)
                if credits is None:
                    credits, rating = clone_totals[e.pk]
                act.credits = -credits
                act.rating = rating
                if act.credits:
                    act.category = "credits"
            acts.append(act)
            if e.kind == Kind.JOINED_CAMPAIGN:
                local[_THE_JOINING] = act
            elif e.kind == Kind.LEFT_CAMPAIGN:
                local[_THE_LEAVING] = act
            if row is not None:
                local[row.pk] = act
                if e.kind in {Kind.PURCHASED, Kind.ADDED, Kind.GRANTED}:
                    act_of.setdefault(row.pk, act)
            elif e.kind == Kind.ROLLED:
                act_of[_roll_key(e.pk)] = act

    # Sources precede dependants, allowing one attachment pass. Add each
    # dependant's balance movement to its containing entry.
    for e, row, ride in waiting:
        home = local.get(ride)
        if home is None:
            acts.append(_one_act(e, row, viewer, alive))
            continue
        # The additions carrier uses the campaign's name and needs no sub-line.
        # Keep the shared campaign type's label beneath the joining entry.
        own_type = e.campaign is not None and (
            row.campaign_type_id == e.campaign.additions_id
        )
        if not own_type:
            home.subs.append(Sub(name=_name(row), kind=_kindword(row)))
        home.credits += -e.credits_delta
        home.trade_points += -e.trade_points_delta
        home.rating += e.rating_delta
        local.setdefault(row.pk, home)
        if e.kind == Kind.GRANTED:
            act_of.setdefault(row.pk, home)


def _caught_up_acts(caught_up, sources, alive):
    """Group propagated grants by source without naming a person as actor.

    Several recipients produce one source entry with a sub-entry per model.
    A single recipient produces a model entry naming the grant's source.
    """
    by_source = {}
    for e, row in caught_up:
        source = sources.get(row.materialised_for_id) if row is not None else None
        by_source.setdefault(source, []).append((e, row))
    for source, group in by_source.items():
        if len(group) == 1:
            e, row = group[0]
            model = _model_of(e, row)
            at = _model_span(model, alive)
            opening = (
                (at, Span(" gained "))
                if model is not None
                else (Span("the gang gained "),)
            )
            tail = (
                (Span(f" — now part of what a {source} comes with"),) if source else ()
            )
            yield (
                Act(
                    when=e.created,
                    actor="",
                    spans=(*opening, Span(_name(row)), *tail),
                    category="kit",
                    miniature_pk=str(model.pk) if model else "",
                    miniature_name=str(model) if model else "",
                ),
                group,
            )
        else:
            first, _ = group[0]
            headline = (
                (Span(f"what a {source} comes with changed"),)
                if source
                else (Span("what the gang's models come with changed"),)
            )
            subs = [
                Sub(
                    name=str(model) if (model := _model_of(e, row)) else "the gang",
                    note=f"gained {_name(row)}",
                )
                for e, row in group
            ]
            yield (
                Act(
                    when=first.created,
                    actor="",
                    spans=headline,
                    subs=subs,
                    category="kit",
                ),
                group,
            )


#: Batch-local joining key for campaign type attachment, distinct from
#: assignment keys.
_THE_JOINING = object()
#: The same for the leaving, which the campaign types removed with it ride.
_THE_LEAVING = object()


def _roll_key(event_pk):
    """How a roll's act is filed in ``act_of``, beside the records' own
    keys and never mistakable for one."""
    return ("roll", event_pk)


def _rides(e, row):
    """What this event rode in on: the record whose act it folds under,
    or None where it stands for itself."""
    if row is None:
        return None
    if e.kind == Kind.GRANTED:
        return row.caused_by_id
    if (
        e.kind in {Kind.REMOVED, Kind.RESTORED, Kind.REFUNDED, Kind.SOLD}
        and not row.removes
    ):
        return row.parent_id or row.caused_by_id
    return None


def _machinery(e, row):
    """Whether an event concerns content omitted from player history.

    Hide internal carriers, included weapon profiles, hidden slots and their
    classification picks. A profile ever priced separately remains visible
    for both acquisition and removal events.
    """
    if e.kind in _COUNTER_MACHINERY:
        return True
    if e.kind == Kind.RATING_SET and e.note.startswith(CLONED_RATING_NOTE_PREFIX):
        return True
    if row is None:
        return False
    if e.kind == Kind.CLONED:
        return True
    if row.hidden_id is not None or row.asset_table_id is not None:
        return True
    if row.slot_id is not None and row.slot.hidden:
        return True
    if row.pickable_id is not None and _settles_a_hidden_slot(row):
        return True
    if row.weapon_profile_id is None:
        return False
    entry = getattr(row, "ledger_entry", None)
    return entry is None or entry.list_price == 0


def _settles_a_hidden_slot(pick):
    """Whether this pick resolves a hidden slot.

    Use its explicit slot or fall back to its source assignment's slot;
    both are loaded with the record.
    """
    slot = pick.chosen_for_slot
    if slot is None and pick.chosen_for is not None:
        slot = pick.chosen_for.slot
    return slot is not None and slot.hidden


def _one_edit_of_what_a_model_is(standing):
    """Whether the batch contains only one model's owner-authored subtype or rule edits.

    Require the owner-edit reason to distinguish these from grants and choices.
    """
    if len(standing) < 2:
        return False
    models = set()
    for e, row in standing:
        if row is None or (row.subtype_id is None and row.rule_id is None):
            return False
        if e.kind not in {Kind.ADDED, Kind.TOOK_AWAY, Kind.REMOVED}:
            return False
        entry = getattr(row, "ledger_entry", None)
        if entry is None or entry.reason != Reason.EDITED:
            return False
        models.add(row.miniature_root_id or row.miniature_id)
    return len(models) == 1


def _is_clean_house(standing):
    """True when one operation's events are all Clean House clearing
    Recovery — the shape ``Operation.clean_house`` writes."""
    return len(standing) > 0 and all(
        e.kind == Kind.STATUS_SET and e.note.endswith(f": {CLEAN_HOUSE}")
        for e, _ in standing
    )


def _clean_house_as_one(standing, viewer, alive):
    """Every model Clean House cleared, as one line with the names beneath."""
    first, _ = standing[0]
    subs = [
        Sub(name=str(e.miniature) if e.miniature else "a model", note="out of Recovery")
        for e, _ in standing
    ]
    models = "model" if len(subs) == 1 else "models"
    return Act(
        when=first.created,
        actor=_actor(first, viewer),
        actor_user=_actor_user(first, viewer),
        actor_pk=first.actor_id,
        spans=(
            Span("cleaned house — "),
            Span(f"{len(subs)} {models} back from Recovery"),
        ),
        subs=subs,
        category="model",
    )


def _edits_as_one(standing, viewer, alive):
    """Combine a batch of one model's subtype and rule edits into one entry."""
    first, first_row = standing[0]
    model = first_row.miniature_root or first_row.miniature
    verb = "reset" if all(e.kind == Kind.REMOVED for e, _ in standing) else "changed"
    subs = []
    for e, row in standing:
        subs.append(Sub(name=_name(row), kind=_kindword(row), note=_turn(e, row)))
    return Act(
        when=first.created,
        actor=_actor(first, viewer),
        actor_user=_actor_user(first, viewer),
        actor_pk=first.actor_id,
        spans=(Span(f"{verb} what "), _model_span(model, alive), Span(" is")),
        subs=subs,
        category="model",
        miniature_pk=str(model.pk) if model else "",
        miniature_name=str(model) if model else "",
    )


def _turn(e, row):
    """Which way one edit went, in a word or two."""
    if e.kind == Kind.ADDED:
        return "added"
    if e.kind == Kind.TOOK_AWAY:
        return "taken away"
    if row is not None and row.removes:
        return "back"
    return "removed"


def _one_act(e, row, viewer, alive):
    spans, category = _tell(e, row, alive)
    model = _model_of(e, row)
    # A grant's sentence already names who gained the thing, and a
    # battle's stake is won or lost by the gang itself.
    told_by_the_gang = (e.kind == Kind.GRANTED and model is not None) or (
        e.kind in HOLDING and e.battle_id is not None
    )
    actor = "" if told_by_the_gang else _actor(e, viewer)
    # A budget's opening correction squares the ledger with what the gang
    # holds; no credits arrived, so the line shows no figure for it.
    credits = 0 if e.kind == Kind.BUDGET_SET else -e.credits_delta
    return Act(
        when=e.created,
        actor=actor,
        actor_user=_actor_user(e, viewer) if actor else None,
        actor_pk=e.actor_id,
        spans=spans,
        credits=credits,
        trade_points=-e.trade_points_delta,
        rating=e.rating_delta,
        note=_shown_note(e),
        category=category,
        miniature_pk=str(model.pk) if model else "",
        miniature_name=str(model) if model else "",
    )


def _movement(note):
    """What a tally moved, as words: "— +1, now 4".

    ``Operation.tally`` writes the movement and where it landed in front
    of whatever reason the caller gave. A note carrying only a reason,
    or none at all, has no movement to state and gives its reason alone.
    """
    movement, _, reason = note.partition(":")
    change, arrow, standing = movement.partition(" → ")
    if not arrow:
        return (Span(f" — {note}"),) if note else ()
    moved = f" — {change}, now {standing}"
    reason = reason.strip()
    return (Span(f"{moved} ({reason})"),) if reason else (Span(moved),)


def _tell(e, row, alive):
    """Return an event's sentence fragments and filter category.

    Start fragments lowercase because the actor precedes them. Model grants
    instead use the receiving model as subject and leave the actor empty.
    """
    thing = Span(_name(row)) if row else Span("something")
    kind = Span(_kindword(row)) if row else Span("")
    model = _model_of(e, row)
    at = _model_span(model, alive)
    identity = row is not None and (
        row.subtype_id is not None or row.rule_id is not None
    )
    category = (
        "credits"
        if e.kind in CREDITS or e.credits_delta
        else "model"
        if e.kind in PERSONAL or identity or e.kind == Kind.TALLIED
        else "kit"
    )

    if _about_a_holding(e):
        if e.battle_id is not None:
            return _tell_stake(e), "gang"
        return _tell_holding(e), "gang"

    match e.kind:
        case Kind.ACTION_USE_STARTED:
            return _tell_action_use(e, "started", alive), "model"
        case Kind.ACTION_USE_PAID:
            return _tell_action_use(e, "paid to use", alive), "credits"
        case Kind.ACTION_USE_COMPLETED:
            return _tell_action_use(e, "completed", alive, result=True), "model"
        case Kind.ACTION_USE_CANCELLED:
            return _tell_action_use(e, "cancelled", alive), "model"
        case Kind.ACTION_USE_APPLIED_BY_HAND:
            return _tell_action_use(e, "applied", alive, after=" by hand"), "model"
        case Kind.ACTION_USE_REOPENED:
            return _tell_action_use(e, "reopened", alive), "model"
        case Kind.ACTION_USE_UNDONE:
            return _tell_action_use(e, "undid", alive, result=True), "model"
        case Kind.ACTION_USE_CORRECTED:
            return _tell_action_use(e, "corrected", alive, result=True), "model"
        case Kind.PURCHASED:
            if row is not None and row.profile_id is not None:
                return (Span("hired "), at, Span(f", a {_name(row)}")), "credits"
            if identity:
                return (
                    Span("bought the "),
                    kind,
                    Span(" "),
                    thing,
                    *_for(model, at),
                ), "credits"
            return (Span("bought "), thing, *_for(model, at)), "credits"
        case Kind.ADDED:
            if row is not None and row.gang_type_id is not None:
                return (Span("created the gang, a "), thing, Span(" gang")), "gang"
            if identity:
                return (
                    Span("added the "),
                    kind,
                    Span(" "),
                    thing,
                    *_for(model, at, "to"),
                ), category
            return (Span("added "), thing, *_for(model, at, "to")), category
        case Kind.GRANTED if row is not None and row.roll_id is not None:
            # A pick whose roll is not in the story — told further back
            # than the page reaches, or not told at all.
            rolled = f", rolled {row.roll.roll}" if row.roll else ""
            return _granted(thing, model, at, rolled), category
        case Kind.GRANTED:
            # Only reached when what caused it is not in the story.
            return _granted(thing, model, at), category
        case Kind.ROLLED:
            # The choice it was for is on the event: what the pick that
            # follows says its kind is, said here before there is a pick.
            asked = f" — {e.slot.choice_label}" if e.slot is not None else ""
            return (
                Span(f"rolled {e.roll} on a {_dice_label(e.dice)}"),
                *_for(model, at),
                Span(asked),
            ), "model" if model is not None else "gang"
        case Kind.TOOK_AWAY:
            return (
                Span("took "),
                thing,
                Span(" away"),
                *_for(model, at, "from"),
            ), "model"
        case Kind.REMOVED if row is not None and row.removes:
            return (Span("put "), thing, Span(" back"), *_for(model, at, "on")), "model"
        case Kind.REMOVED:
            return (
                Span("removed "),
                thing,
                *_stood_at(e),
                *_for(model, at, "from"),
            ), category
        case Kind.RESTORED:
            return (
                Span("restored "),
                thing,
                *_stood_at(e),
                *_for(model, at, "on"),
            ), category
        case Kind.REFUNDED:
            return (Span("returned "), thing, Span(" for a refund")), "credits"
        case Kind.SOLD:
            return (Span("sold "), thing), "credits"
        case Kind.REPRICED:
            return (Span("the price of "), thing, Span(" changed")), "credits"
        case Kind.RATING_SET:
            return (Span("changed "), at, Span("'s base rating")), "model"
        case Kind.RATING_RESET:
            return (Span("reset "), at, Span("'s base rating")), "model"
        case Kind.AMENDED:
            return (Span("changed "), thing), "credits"
        case Kind.MOVED:
            return (Span("moved "), thing), "kit"
        case Kind.TALLIED:
            return (
                Span("changed "),
                thing,
                *_for(model, at, "on"),
                *_movement(e.note),
            ), "model"
        case Kind.STATUS_SET:
            return _status_told(e, model, at), "model"
        case Kind.TRANSFERRED:
            # Positive left this gang, negative arrived. The counterpart
            # is named plain: a gang's history is about this gang, and the
            # other one has its own page.
            other = e.counterpart.name if e.counterpart else "another gang"
            figure = f"{abs(e.credits_delta)}¢"
            because = (Span(f" — {e.note}"),) if e.note else ()
            if e.credits_delta > 0:
                return (Span(f"paid {figure} to {other}"), *because), "credits"
            return (Span(f"received {figure} from {other}"), *because), "credits"
        case Kind.INCOME:
            amount = -e.credits_delta
            # A later revision of a post-battle report corrects the first.
            revision = e.post_battle_revision
            correcting = revision is not None and revision.sequence > 1
            sign = "+" if amount >= 0 else "−"
            wording = (
                f"received {amount}¢"
                if amount >= 0 and not correcting
                else f"corrected credits by {sign}{abs(amount)}¢"
            )
            because = (Span(f" — {e.note}"),) if e.note else ()
            return (Span(wording), *because), "credits"
        case Kind.CREDITS_ADJUSTED:
            verb = "added" if e.credits_delta < 0 else "removed"
            because = (Span(f" — {e.note}"),) if e.note else ()
            return (Span(f"{verb} {abs(e.credits_delta)}¢"), *because), "credits"
        case Kind.POST_BATTLE:
            revision = e.post_battle_revision
            href = (
                reverse(
                    "n26-post-battle-revision",
                    args=[revision.report_id, revision.sequence],
                )
                if revision
                else ""
            )
            return (Span("recorded "), Span("post-battle results", href)), "gang"
        case Kind.RENAMED:
            was, _, now = e.note.rpartition(" → ")
            # About no model, so about the gang: the same act one level up.
            whose = "model" if model is not None else "gang"
            if model is None:
                if was:
                    return (Span(f"renamed the gang {was} to {now}"),), "gang"
                return (Span("renamed the gang"),), "gang"
            if was:
                return (Span(f"renamed {was} to "), Span(now, at.href)), whose
            return (Span("renamed "), at), whose
        case Kind.CLONED:
            source, _, _ = clone_event_details(e.note)
            if model is not None:
                return (Span(f"cloned {source or 'another model'} as "), at), "model"
            if source:
                return (Span(f"cloned the gang from {source}"),), "gang"
            return (Span("cloned the gang"),), "gang"
        case Kind.JOINED_CAMPAIGN | Kind.LEFT_CAMPAIGN:
            # The actor added the gang; Joined would incorrectly describe the
            # actor as joining. The enclosing history already identifies the gang.
            where = e.campaign.name if e.campaign else "a campaign"
            if e.kind == Kind.JOINED_CAMPAIGN:
                return (Span(f"added the gang to {where}"),), "gang"
            return (Span(f"took the gang out of {where}"),), "gang"
        case Kind.BUDGET_SET:
            _, _, now = e.note.rpartition(" → ")
            if now == NO_CEILING:
                return (Span("lifted the budget — the gang spends freely"),), "credits"
            if now:
                return (Span(f"set the budget to {now}"),), "credits"
            return (Span("changed the budget"),), "credits"
        # A trip to the trading post wrote these before it was an action
        # of its own. Nothing writes them now; the sentences stay so that
        # a gang's older history still reads. Finishing says "completed",
        # the word an action's own ending uses, so a gang that visited
        # either side of the change reads as one story.
        case Kind.TRADE_POINTS_SET if e.note == "closed":
            return (Span("completed the Visit Trading Post action"),), "credits"
        case Kind.TRADE_POINTS_SET:
            brought = e.note
            if brought == "1":
                return (Span("visited the Trading Post with 1 Trade Point"),), "credits"
            if brought:
                return (
                    Span(f"visited the Trading Post with {brought} Trade Points"),
                ), "credits"
            return (Span("visited the Trading Post"),), "credits"
        case Kind.ACTION_OPENED:
            named, brought = read_note(e.note)
            label = f"the {named} action" if named else "an action"
            text = f"started {label}"
            if brought is not None:
                text += f" with {_points(brought)}"
            return (
                Span(text),
                *_for(model, at),
            ), "model" if model is not None else "gang"
        case Kind.ACTION_CLOSED:
            named, left = read_note(e.note)
            label = f"the {named} action" if named else "an action"
            text = f"completed {label}"
            if left is not None and left > 0:
                text += f", discarding {_points(left, True)}"
            return (
                Span(text),
                *_for(model, at),
            ), "model" if model is not None else "gang"
        case Kind.VISITED_TRADING_POST:
            # Use the recorded source of contributed Trade Points when available.
            # A bare total does not describe the fighter's rank.
            went_as = f" as {e.note}" if e.note and not e.note.isdigit() else ""
            return (
                Span("sent "),
                at,
                Span(f"{went_as} to the trading post"),
            ), "credits"
        case Kind.TOOLKIT_TAG:
            return (Span(e.note[:1].lower() + e.note[1:]),), "gang"
        case Kind.NOTED:
            # About no model, so about the gang — as a rename is.
            if model is None:
                return (Span("edited the gang's notes"),), "gang"
            return (Span("edited "), at, Span("'s notes")), "model"
        case Kind.LORE_EDITED:
            if model is None:
                return (Span("edited the gang's lore"),), "gang"
            return (Span("edited "), at, Span("'s lore")), "model"
        case Kind.IMAGE_SET:
            if model is None:
                return (Span("gave the gang a picture"),), "gang"
            return (Span("gave "), at, Span(" a picture")), "model"
        case Kind.IMAGE_CLEARED:
            if model is None:
                return (Span("removed the gang's picture"),), "gang"
            return (Span("removed "), at, Span("'s picture")), "model"
        case Kind.STAT_SET:
            said, _, now = e.note.rpartition(" → ")
            stat, _, was = said.rpartition(" ")
            if stat:
                return (Span("set "), at, Span(f"'s {stat} to {now}")), "model"
            return (Span("set a characteristic of "), at), "model"
        case Kind.STAT_CLEARED:
            # The note reads "WS 4+ cleared — 3+ prints again": the
            # first word names the characteristic.
            stat = e.note.split(" ")[0] if e.note else ""
            if stat:
                return (Span("cleared "), at, Span(f"'s {stat}")), "model"
            return (Span("cleared a characteristic of "), at), "model"
    return (Span(e.get_kind_display().casefold()),), category


def _tell_action_use(e, verb, alive, *, result=False, after=""):
    """Tell an action event from the names captured when it was written."""
    record = e.action_record
    fighter = e.miniature or (record.fighter if record is not None else None)
    action = (record.source or {}).get("name") if record is not None else ""
    action = action or (e.note if not result else "") or "an action"
    outcome = f" — {e.note}" if result and e.note else ""
    return (
        Span(f"{verb} {action}{after}"),
        *_for(fighter, _model_span(fighter, alive)),
        Span(outcome),
    )


def _about_a_holding(e):
    """Whether this record is a campaign's asset coming to the gang or
    leaving it. The two kinds are written for nothing else."""
    return e.kind in HOLDING


def _holding_name(e):
    """The asset an event is about, linked to its detail page while
    it still stands. One removed from the campaign since is named from the
    note, which kept the name for exactly this: the line still says what
    the gang gained or lost."""
    campaign_asset = e.campaign_asset
    if campaign_asset is None:
        return Span(e.note or "an asset")
    return Span(
        str(campaign_asset),
        reverse(
            "n26-campaign-asset", args=[campaign_asset.campaign_id, campaign_asset.pk]
        ),
    )


def _tell_stake(e):
    """A battle's stake moving, as the gang's own history says it: "Won
    Old Ruins in Stand-off", or, for the move a correction wrote to undo
    an earlier one, "Got Old Ruins back after Stand-off was corrected"."""
    battle = e.battle.title
    name = _holding_name(e)
    gained = e.kind == Kind.GAINED
    if e.reversal_of_id is not None:
        verb = "Got " if gained else "Returned "
        after = " back" if gained else ""
        return (
            Span(verb),
            name,
            Span(f"{after} after {battle} was corrected"),
        )
    return (Span("Won " if gained else "Lost "), name, Span(f" in {battle}"))


def _tell_holding(e):
    """A campaign's asset the gang gained or lost, as the gang's own
    history says it: "gained the territory Old Ruins". Which gang goes
    unsaid, as for joining — the gang's own history is already about it.
    """
    campaign_asset = e.campaign_asset
    sort = f"the {campaign_asset.type_label} " if campaign_asset is not None else ""
    verb = "gained " if e.kind == Kind.GAINED else "lost "
    return (Span(verb + sort), _holding_name(e))


def _action_named(note):
    """The action's own name, read from the kind its note holds.

    Empty for a note naming no kind this edition has, which leaves the
    sentence saying an action was started without inventing which.
    """
    from n26.core.models import Activity

    try:
        return Activity.Kind(note).label
    except ValueError:
        return ""


def _points(figure, unspent=False):
    """A figure of Trade Points as a sentence can carry it."""
    noun = "unspent Trade Point" if unspent else "Trade Point"
    if figure == 0:
        return f"no {noun}s"
    if figure == 1:
        return f"1 {noun}"
    return f"{figure} {noun}s"


def _status_told(e, model, at):
    """The sentence for a status change, from a note of "was → now" and,
    after a colon, what did it."""
    from n26.core.status import Status

    movement, _, why = e.note.partition(":")
    _, _, now = movement.partition(" → ")
    now = now.strip()
    why = why.strip()
    because = (Span(f" — {why}"),) if why and why != CLEAN_HOUSE else ()
    # Spans start lowercase with the verb: the actor's name goes in front.
    match now:
        case Status.RECOVERY:
            return (Span("put "), at, Span(" into Recovery"), *because)
        case Status.CRITICAL:
            return (Span("marked "), at, Span(" as Critically Injured"), *because)
        case Status.CAPTURED:
            return (Span("marked "), at, Span(" as captured"), *because)
        case Status.RANSOMED:
            return (Span("marked "), at, Span(" as held for ransom"), *because)
        case Status.DEAD:
            return (Span("marked "), at, Span(" as dead"), *because)
        case Status.ACTIVE if why == CLEAN_HOUSE:
            return (Span("cleared Recovery for "), at)
        case Status.ACTIVE:
            return (Span("marked "), at, Span(" as active"), *because)
    return (Span("changed the status of "), at)


def _dice_label(dice):
    from n26.library.models import Dice

    return Dice.label_for(dice)


def _granted(thing, model, at, rolled=""):
    """A grant as the model gaining the thing.

    The fighter is the subject. Naming the person who recorded it as
    the one who gained the effect reads as if they received it. A
    caught-up grant is already told this way.
    """
    if model is not None:
        return (at, Span(" gained "), thing, Span(rolled))
    return (Span("gained "), thing, Span(rolled))


def _for(model, at, word="for"):
    """(" for ", {model}) with the name linked, or nothing where the
    act has no model."""
    if model is None:
        return ()
    return (Span(f" {word} "), at)


#: Structured notes already represented in the main sentence must not
#: also appear as raw bookkeeping beneath it.
_NOTE_IS_MACHINERY = {
    Kind.CLONED,
    Kind.TOOLKIT_TAG,
    Kind.STATUS_SET,
    Kind.TRANSFERRED,
    Kind.INCOME,
    Kind.CREDITS_ADJUSTED,
    Kind.POST_BATTLE,
    Kind.TRADE_POINTS_SET,
    Kind.VISITED_TRADING_POST,
    Kind.TALLIED,
    Kind.ACTION_OPENED,
    Kind.ACTION_CLOSED,
    Kind.ACTION_USE_STARTED,
    Kind.ACTION_USE_PAID,
    Kind.ACTION_USE_COMPLETED,
    Kind.ACTION_USE_CANCELLED,
    Kind.ACTION_USE_CORRECTED,
    Kind.ACTION_USE_APPLIED_BY_HAND,
    Kind.ACTION_USE_REOPENED,
    Kind.ACTION_USE_UNDONE,
}


def _shown_note(e):
    """The note, where it is the player's words rather than a record the
    sentence already told."""
    if e.kind in {Kind.RENAMED, Kind.STAT_SET, Kind.STAT_CLEARED}:
        return e.note
    if e.kind in _NOTE_IS_MACHINERY:
        return ""
    if e.note == "reset":
        return ""
    # The value an archived counter stood at, which the sentence has said.
    if e.note.startswith(ARCHIVED_COUNTER_NOTE_PREFIX):
        return ""
    # A holding's note is its name, which the sentence has already said.
    if _about_a_holding(e):
        return ""
    return e.note


def _actor(e, viewer):
    if e.actor is None:
        return ""
    if viewer is not None and e.actor_id == getattr(viewer, "id", None):
        return "You"
    return e.actor.username


def _actor_user(e, viewer):
    """The person ``_actor`` names, or None where it names nobody or the
    reader."""
    if e.actor is None:
        return None
    if viewer is not None and e.actor_id == getattr(viewer, "id", None):
        return None
    return e.actor


def _name(row):
    thing = row.assignable if row else None
    return str(thing) if thing is not None else "something"


def _kindword(row):
    """Return the public kind label, using a pick's slot type when needed.

    Slot types name categories such as Gang Legacy or Path. Slot labels
    identify individual choices and are unsuitable as kind labels.
    """
    thing = row.assignable if row else None
    if thing is None:
        return ""
    if row.chosen_for_slot_id is not None and row.chosen_for_slot is not None:
        return row.chosen_for_slot.slot_type.name.lower()
    return kind_of(thing)


def _model_of(e, row):
    if e.miniature is not None:
        return e.miniature
    if row is not None:
        return row.miniature_root or row.miniature
    return None


def _model_span(model, alive):
    """The model's name, linked to its page only while it has one."""
    if model is None:
        return Span("")
    if model.pk not in alive:
        return Span(str(model))
    return Span(str(model), reverse("n26-equip", args=[model.pk]))


def asset_ownership_history(campaign_asset):
    """Recorded ownership changes for this exact holding, oldest first.

    Pool-add events did not store the holding's identity. They are not
    guessed from names, which can be shared by several territories.
    """
    events = (
        LedgerEvent.objects.filter(
            campaign=campaign_asset.campaign,
            campaign_asset=campaign_asset,
            kind__in=(Kind.GAINED, Kind.LOST),
        )
        .select_related("gang", "campaign_asset__asset__asset_type")
        .order_by("created", "id")
    )
    return [act for _, act in _holding_acts(events)]


def campaign_history(campaign, viewer=None, limit=None):
    """Merge campaign events and member gangs' events, oldest first.

    ``limit`` retains the newest entries. Read up to that limit from each
    source, merge in time order, then trim the combined result.
    """
    dated = [
        *_campaign_own_acts(campaign, viewer, limit),
        *_gang_acts_in_campaign(campaign, viewer, limit),
    ]
    dated.sort(key=lambda row: row[0])
    if limit is not None:
        dated = dated[-limit:]
    return [act for _, act in dated]


def load_actor_badges(acts):
    """Load profiles and badge grants for the final displayed set of actors.

    Bounded history queries may already join profiles; unbounded queries
    omit them to avoid widening every event before pagination. Load missing
    profiles and badge grants after merging and paging, keyed by the displayed
    actors. Entries naming no actor or the viewer require no badge reads.
    """
    from django.db.models import prefetch_related_objects

    people = [act.actor_user for act in acts if act.actor_user is not None]
    if people:
        prefetch_related_objects(people, "profile", "badge_grants")


def _joining_companions():
    """Automatic grants in a join share its mark; only the join is a campaign act.

    Exclude companions before taking the recent window so they cannot displace
    the join. The gang's own history keeps the full acquisition detail.
    """
    from django.db.models import Exists, OuterRef, Q

    return ~Q(kind=Kind.JOINED_CAMPAIGN) & Exists(
        LedgerEvent.objects.filter(
            campaign_id=OuterRef("campaign_id"),
            gang_id=OuterRef("gang_id"),
            batch=OuterRef("batch"),
            kind=Kind.JOINED_CAMPAIGN,
        )
    )


def _archiving_companions():
    """Find gang events sharing a campaign counter or label archive batch.

    Only the campaign event appears in the campaign history. Gang histories
    retain their own removal or restoration entries.
    """
    from django.db.models import Exists, OuterRef

    return Exists(
        CampaignEvent.objects.filter(
            campaign_id=OuterRef("campaign_id"),
            batch=OuterRef("batch"),
            kind__in=(
                CampaignEvent.Kind.COUNTER_ARCHIVED,
                CampaignEvent.Kind.LABEL_ARCHIVED,
                CampaignEvent.Kind.COUNTER_UNARCHIVED,
                CampaignEvent.Kind.LABEL_UNARCHIVED,
            ),
        )
    )


def campaign_history_size(campaign):
    """Estimate displayed campaign entries without building their display structures.

    Exclude grants nested under source entries and campaign type grants nested
    under joining events, so the count approximates visible history lines.
    """
    from django.db.models import Exists, OuterRef, Q

    riders = Q(kind=Kind.GRANTED) & (
        Q(assignment__caused_by__isnull=False)
        | Q(assignment__campaign_type__isnull=False)
    )
    # A hand-over is two records under one mark and one line in the log.
    handed_over = Q(kind=Kind.LOST) & Exists(
        LedgerEvent.objects.filter(batch=OuterRef("batch"), kind=Kind.GAINED)
    )
    return (
        campaign.events.count()
        + campaign.gang_events.exclude(_joining_companions())
        .exclude(_archiving_companions())
        .exclude(riders)
        .exclude(handed_over)
        .exclude(kind=Kind.CLONED, assignment__isnull=False)
        .exclude(kind=Kind.RATING_SET, note__startswith=CLONED_RATING_NOTE_PREFIX)
        .exclude(kind__in=_COUNTER_MACHINERY)
        .count()
    )


def _campaign_own_acts(campaign, viewer, limit=None):
    """What the arbitrator changed about the campaign itself, one act each."""
    # Join profiles only for bounded reads. Unbounded histories load the
    # final page's missing profiles and badge grants through load_actor_badges.
    events = campaign.events.select_related(
        "actor",
        "battle",
        "about_user",
        "roll",
        "roll__gang",
        "roll__miniature",
        "roll__battle",
    )
    if limit is not None:
        events = events.select_related("actor__profile")
    # Newest first while the database is doing the cutting, so a limit takes
    # the recent end; the caller sorts the merged result back into order.
    events = (
        events.order_by("-created", "-id")[:limit]
        if limit is not None
        else events.order_by("created", "id")
    )
    events = list(events)
    catalogue = None
    if any(e.kind == CampaignEvent.Kind.SCENARIO_SAVED for e in events):
        from n26.library.scenario_tables import load_catalogue

        catalogue = load_catalogue()
    for e in events:
        yield (e.created, str(e.pk)), _one_campaign_act(e, viewer, catalogue)


def _gang_acts_in_campaign(campaign, viewer, limit=None):
    """Build member gang events recorded during this campaign's memberships.

    Use the gang history renderer so grouping and dependent entries match.
    Process each gang separately to prevent cross-gang batch attachment.
    """
    from n26.core.models import LedgerEvent, Miniature

    events = (
        LedgerEvent.objects.filter(campaign=campaign)
        .exclude(_joining_companions())
        .exclude(_archiving_companions())
        # Exclude clone ledger openings from pagination. The standalone clone
        # event already records the visible change and presentation totals.
        .exclude(kind=LedgerEvent.Kind.CLONED, assignment__isnull=False)
        .exclude(kind=Kind.RATING_SET, note__startswith=CLONED_RATING_NOTE_PREFIX)
        # An opening establishes a counter's ledger. It is not a campaign
        # act, even when the counter arrived while joining the campaign.
        .exclude(kind__in=_COUNTER_MACHINERY)
        .select_related(
            "miniature",
            "actor",
            "action_record__fighter",
            "post_battle_revision",
            "gang",
            "campaign",
            "campaign_asset__asset__asset_type",
            "counterpart",
        )
    )
    if limit is not None:
        # A page brings each actor's profile with the acts; see
        # _campaign_own_acts.
        events = events.select_related("actor__profile")
    events = (
        events.order_by("-created", "-id")[:limit]
        if limit is not None
        else events.order_by("created", "id")
    )
    # A limited read takes the newest; telling them needs them oldest first,
    # because a rider is told after the thing it rode.
    events = sorted(events, key=lambda e: (e.created, str(e.pk)))
    if not events:
        return

    # An asset gained or lost is told as the campaign's own sentence, which
    # names the gangs rather than riding under one gang's line, and a
    # hand-over — LOST on one gang and GAINED on another under one mark —
    # is one act, not two.
    holdings = [e for e in events if e.kind in HOLDING]
    for when, act in _holding_acts(holdings):
        yield when, act
    events = [e for e in events if e.kind not in HOLDING]
    if not events:
        return

    rows = _rows_for(events)
    _name_the_rolls(events, rows)
    _name_the_named_picks(events, rows)
    sources = _comes_with_sources(events, rows)
    # Only the living have a page to link to, across every gang here.
    alive = set(
        Miniature.objects.filter(
            membership__gang__campaign_memberships__campaign=campaign,
            membership__archived=False,
        ).values_list("pk", flat=True)
    )

    by_gang = {}
    for e in events:
        by_gang.setdefault(e.gang_id, []).append(e)

    for gang_id, theirs in by_gang.items():
        acts = []
        act_of = {}
        for cluster in _clusters(theirs):
            _tell_cluster(cluster, rows, acts, act_of, viewer, alive, sources)
        # Whose acts these were, so the campaign's log can say it on every
        # line — the one thing a gang's own history never has to.
        named = theirs[0].gang.name if theirs[0].gang_id else ""
        for act in acts:
            act.gang_pk = str(gang_id)
            act.gang_name = named
            yield (act.when, str(gang_id)), act


def _holding_acts(events):
    """Build one ownership entry per asset transfer, oldest first.

    Combine LOST and GAINED events sharing a batch. Describe the asset and
    its gangs without naming an actor; each gang's history names the person.
    """
    by_mark = {}
    for e in events:
        by_mark.setdefault(e.batch or e.pk, []).append(e)
    for marked in by_mark.values():
        lost = next((e for e in marked if e.kind == Kind.LOST), None)
        gained = next((e for e in marked if e.kind == Kind.GAINED), None)
        first = marked[0]
        name = _holding_name(first)
        if lost is not None and gained is not None:
            spans = (
                name,
                Span(f" went from {_gang_named(lost)} to {_gang_named(gained)}"),
            )
        elif gained is not None:
            spans = (name, Span(f" went to {_gang_named(gained)}"))
        else:
            spans = (Span(f"{_gang_named(lost)} lost "), name)
        yield (
            (first.created, str(first.pk)),
            Act(
                when=first.created,
                actor="",
                spans=spans,
                category="gang",
                actor_pk=first.actor_id,
                related_gang_pks=tuple(dict.fromkeys(str(e.gang_id) for e in marked)),
            ),
        )


def _gang_named(e):
    return e.gang.name if e.gang_id else "a gang"


def _one_campaign_act(e, viewer, catalogue=None):
    spans, category = _tell_campaign(e, catalogue)
    return Act(
        when=e.created,
        actor=_actor(e, viewer),
        actor_user=_actor_user(e, viewer),
        actor_pk=e.actor_id,
        spans=spans,
        category=category,
        note=e.note if e.kind == CampaignEvent.Kind.DICE_ROLL_NOTED else "",
        gang_pk=str(e.roll.gang_id) if e.roll_id and e.roll.gang_id else "",
        gang_name=e.roll.gang.name if e.roll_id and e.roll.gang_id else "",
    )


def _scenario_href(campaign_id, rolls):
    """The generator's address for a saved scenario."""
    from urllib.parse import urlencode

    path = reverse("n26-scenario-generator", args=[campaign_id])
    return f"{path}?{urlencode(rolls)}#scenario"


def _tell_campaign(e, catalogue=None):
    """Build lowercase fragments for a campaign event following its actor.

    Campaign events describe no credit movement.
    """
    kinds = CampaignEvent.Kind
    match e.kind:
        case kinds.CREATED:
            if e.note:
                return (Span(f"set the campaign up on {e.note}"),), "campaign"
            return (Span("set the campaign up"),), "campaign"
        case kinds.RENAMED:
            was, _, now = e.note.rpartition(" → ")
            if was:
                return (Span(f"renamed the campaign {was} to {now}"),), "campaign"
            return (Span("renamed the campaign"),), "campaign"
        case kinds.BUDGET_SET:
            _, _, now = e.note.rpartition(" → ")
            if now == NO_CEILING:
                return (Span("removed the gang budget"),), "campaign"
            if now:
                return (Span(f"set the gang budget to {now}¢"),), "campaign"
            return (Span("changed the gang budget"),), "campaign"
        case kinds.STATUS_CHANGED:
            _, _, now = e.note.rpartition(" → ")
            return (Span(f"set the campaign status to {now}"),), "campaign"
        case kinds.SCHEDULE_EDITED:
            return (Span("edited the campaign schedule"),), "campaign"
        case kinds.CYCLE_TRANSITION:
            return (Span(f"changed the current cycle: {e.note}"),), "campaign"
        case kinds.STARTING_MODE_SET:
            return (
                Span(f"changed starting territories: {e.note.lower()}"),
            ), "campaign"
        case kinds.GROUPING_CHANGED:
            return (Span("changed the gang grouping and colours"),), "campaign"
        case kinds.SUMMARY_EDITED:
            return (Span("edited the campaign's summary"),), "campaign"
        case kinds.ARCHIVED:
            return (Span("archived the campaign"),), "campaign"
        case (
            kinds.INVITED
            | kinds.INVITE_ACCEPTED
            | kinds.INVITE_DECLINED
            | kinds.PLAYER_REMOVED
            | kinds.PLAYER_LEFT
        ):
            # Acceptance and departure already name the player as actor. Invitations
            # and removals need the affected player's name after the arbitrator.
            who = e.about_user.username if e.about_user_id else "somebody"
            match e.kind:
                case kinds.INVITED:
                    return (Span(f"invited {who}"),), "campaign"
                case kinds.INVITE_ACCEPTED:
                    return (Span("accepted the invitation"),), "campaign"
                case kinds.INVITE_DECLINED:
                    return (Span("declined the invitation"),), "campaign"
                case kinds.PLAYER_LEFT:
                    return (Span("left the campaign"),), "campaign"
            return (Span(f"removed {who} from the campaign"),), "campaign"
        case kinds.DICE_ROLLED | kinds.DICE_ROLL_NOTED:
            if not e.roll_id:
                text = (
                    "updated an outcome note for a dice roll"
                    if e.kind == kinds.DICE_ROLL_NOTED
                    else "recorded a dice roll"
                )
                return (Span(text),), "campaign"
            roll = e.roll
            href = reverse("n26-campaign-roll", args=[e.campaign_id, roll.pk])
            if e.kind == kinds.DICE_ROLL_NOTED:
                verb = (
                    "updated an outcome note" if e.note else "cleared the outcome note"
                )
                return (Span(f"{verb} for {roll.reason}", href),), "campaign"
            spans = [
                Span(
                    f"recorded {roll.calculation} ({roll.get_source_display()}) for {roll.reason}",
                    href,
                )
            ]
            if roll.miniature_id:
                spans.append(Span(f" · model: {roll.miniature.name}"))
            if roll.battle_id:
                spans.append(
                    Span(
                        f" in {roll.battle.title}",
                        reverse("n26-battle", args=[e.campaign_id, roll.battle_id]),
                    )
                )
            return tuple(spans), "campaign"
        case kinds.SCENARIO_SAVED:
            # The note holds each table's roll and the scenario's name. The
            # entries are named from the tables as they are now, and the
            # line links to the generator showing the same scenario.
            from n26.core.scenarios import describe, read_history_note, results

            rolls, name = read_history_note(e.note)
            found = results(rolls, catalogue)
            what = f"saved the scenario {name}" if name else "saved a scenario"
            if not found:
                return (Span(what),), "campaign"
            return (
                Span(
                    f"{what}: {describe(found)}", _scenario_href(e.campaign_id, rolls)
                ),
            ), "campaign"
        case kinds.BATTLE_RECORDED:
            href = (
                reverse("n26-battle", args=[e.campaign_id, e.battle_id])
                if e.battle_id
                else ""
            )
            if e.note:
                return (Span(f"recorded {e.note}", href),), "campaign"
            when = e.battle.date if e.battle else None
            if when:
                return (
                    Span(f"recorded a battle fought on {when:%-d %B}", href),
                ), "campaign"
            return (Span("recorded a battle"),), "campaign"
        case kinds.BATTLE_EDITED:
            href = (
                reverse("n26-battle", args=[e.campaign_id, e.battle_id])
                if e.battle_id
                else ""
            )
            return (Span(f"edited the battle: {e.note}", href),), "campaign"
        case kinds.BATTLE_ARCHIVED:
            href = (
                reverse("n26-battle", args=[e.campaign_id, e.battle_id])
                if e.battle_id
                else ""
            )
            return (Span(f"archived the battle: {e.note}", href),), "campaign"
        case kinds.BATTLE_REMOVED:
            if e.note:
                return (Span(f"removed the battle of {e.note}"),), "campaign"
            return (Span("removed a battle"),), "campaign"
        case kinds.BATTLE_RESTORED:
            href = (
                reverse("n26-battle", args=[e.campaign_id, e.battle_id])
                if e.battle_id
                else ""
            )
            return (Span(f"restored the battle: {e.note}", href),), "campaign"
        case kinds.ASSET_ADDED:
            # Use the recorded name even if the asset has since been deleted.
            what = f"the asset {e.note}" if e.note else "an asset"
            return (Span(f"added {what}"),), "campaign"
        case kinds.ASSET_REMOVED:
            what = f"the asset {e.note}" if e.note else "an asset"
            return (Span(f"removed {what}"),), "campaign"
        case kinds.ASSET_EDITED:
            return (Span(f"edited an asset: {e.note}"),), "campaign"
        case kinds.ASSET_ROLLED:
            # The note stores a complete sentence plus an optional manual-roll marker.
            # Remove only that trailing marker, then lowercase the sentence after the
            # actor. Internal full stops can belong to authored table or gang names.
            from n26.core.operations import ROLL_ENTERED, ROLL_ENTERED_BEFORE

            said, manual = e.note, False
            for marker in (ROLL_ENTERED, ROLL_ENTERED_BEFORE):
                if said.endswith(f" {marker}"):
                    said, manual = said[: -(len(marker) + 1)], True
                    break
            if not said:
                return (Span("made a roll"),), "campaign"
            said = said[0].lower() + said[1:].removesuffix(".")
            if manual:
                said = f"{said} (manual roll)"
            return (Span(said),), "campaign"
        case kinds.TABLE_OPENED:
            what = f"the table {e.note}" if e.note else "a table"
            return (Span(f"made {what} available to every gang"),), "campaign"
        case kinds.TABLE_CLOSED:
            what = f"the table {e.note}" if e.note else "a table"
            return (Span(f"withdrew {what}"),), "campaign"
        case kinds.TABLE_CREATED:
            what = f"the table {e.note}" if e.note else "a table"
            return (Span(f"created {what}"),), "campaign"
        case kinds.ASSET_TYPE_ADDED:
            what = f"the asset type {e.note}" if e.note else "an asset type"
            return (Span(f"added {what}"),), "campaign"
        case kinds.ASSET_TYPE_EDITED:
            was, _, now = e.note.rpartition(" → ")
            if was:
                return (
                    Span(f"edited the asset type {was}, now called {now}"),
                ), "campaign"
            what = f"the asset type {now}" if now else "an asset type"
            return (Span(f"edited {what}"),), "campaign"
        case kinds.ASSET_CREATED:
            what = f"the asset {e.note}" if e.note else "an asset"
            return (Span(f"created {what}"),), "campaign"
        case kinds.PLAYER_TAGGED:
            return (Span(e.note[:1].lower() + e.note[1:]),), "campaign"
        case kinds.COUNTER_ADDED:
            # The note holds the name and the opening value, as a budget
            # note holds its two figures.
            name, _, opening = e.note.rpartition(" → ")
            if name:
                return (
                    Span(f"added the counter {name}, opening at {opening}"),
                ), "campaign"
            return (Span("added a counter"),), "campaign"
        case kinds.LABEL_ADDED:
            name, _, options = e.note.partition(" → ")
            if options:
                return (
                    Span(f"added the label {name}, with the options {options}"),
                ), "campaign"
            if name:
                return (Span(f"added the label {name}"),), "campaign"
            return (Span("added a label"),), "campaign"
        case kinds.COUNTER_ARCHIVED:
            what = f"the counter {e.note}" if e.note else "a counter"
            return (Span(f"archived {what}"),), "campaign"
        case kinds.LABEL_ARCHIVED:
            what = f"the label {e.note}" if e.note else "a label"
            return (Span(f"archived {what}"),), "campaign"
        case kinds.COUNTER_UNARCHIVED:
            what = f"the counter {e.note}" if e.note else "a counter"
            return (Span(f"unarchived {what}"),), "campaign"
        case kinds.LABEL_UNARCHIVED:
            what = f"the label {e.note}" if e.note else "a label"
            return (Span(f"unarchived {what}"),), "campaign"
    return (Span("changed the campaign"),), "campaign"
