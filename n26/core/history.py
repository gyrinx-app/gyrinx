"""A gang's history and a campaign's, told plainly.

Reads the ledger's events and turns them into something a player can
read: one act per line, in their own words — hired, bought, renamed,
took away, put back. The machinery underneath stays underneath: nothing
here says "assignment" or "batch", a bookkeeping row a player never saw
is never shown, and a weapon's own firing line folds into the weapon
rather than earning a line of its own.

Structures before renderers: the view gets a flat list of acts as plain
dataclasses, filters and groups them, and the template draws the result.

Three readings are not literal:

* Events written by one operation share a mark, and marked neighbours
  that all edit what one model is are told as a single act — a reset
  that archived six records is one line with six sub-lines, not six.
* A granted thing folds under the act that caused it: a hire reads as
  "hired Krago" with what came with him listed beneath, not as seven
  lines of equal weight.
* Archiving a taken-away subtype *restores* the subtype, so that event
  reads "put Mounted back", never "removed Mounted" — the record is of
  the undoing, and the plain kind would say the opposite of what
  happened.
"""

from dataclasses import dataclass, field

from django.urls import reverse

from n26.core.campaigns import NO_CEILING
from n26.core.cloning import clone_event_details
from n26.core.effects import kind_of
from n26.core.models import Assignment, CampaignEvent, LedgerEvent, Reason
from n26.core.models.action import read_note
from n26.core.operations import CLEAN_HOUSE

Kind = LedgerEvent.Kind

#: The kinds that concern money. "Amended" is here because re-choosing
#: how a thing is built can change what it charges.
MONEY = {
    Kind.PURCHASED,
    Kind.REFUNDED,
    Kind.SOLD,
    Kind.REPRICED,
    Kind.AMENDED,
    Kind.TRANSFERRED,
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
}


@dataclass(frozen=True)
class Span:
    """One stretch of a sentence, linked if ``href`` says where to."""

    text: str
    href: str = ""


@dataclass(frozen=True)
class Sub:
    """One line folded under an act: a thing that came with it, went
    with it, or moved in the same breath."""

    name: str
    kind: str = ""
    note: str = ""

    @property
    def detail(self):
        """What follows the name, ready to draw — either part may be
        empty, and a rider whose kind the page never names shows only
        which way it went."""
        return ", ".join(part for part in (self.kind, self.note) if part)


@dataclass
class Act:
    """One thing done to the gang, in the player's words.

    ``credits`` and ``rating`` carry the player's reading of the money:
    negative credits left the pot, positive came back. ``trade_points``
    reads the same way, and is its own figure rather than more money: it
    belongs to a Visit Trading Post action and dies with it. ``actor`` is the
    subject the sentence starts with, or empty where nobody in
    particular did it. ``category`` and ``miniature_pk`` exist for the
    page's filters; ``search`` is every word worth matching against.
    """

    when: object
    actor: str
    spans: tuple[Span, ...]
    credits: int = 0
    trade_points: int = 0
    rating: int = 0
    note: str = ""
    subs: list[Sub] = field(default_factory=list)
    category: str = "kit"
    miniature_pk: str = ""
    miniature_name: str = ""
    #: Whose act it was, where the reader holds more than one gang's. A gang's
    #: own history leaves these empty: there is only ever the one.
    gang_pk: str = ""
    gang_name: str = ""

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


def build(gang, viewer=None):
    """Every act in this gang's history, oldest first.

    ``viewer`` names who is reading: their own acts say "You", anyone
    else's say the actor's name. A fixed number of queries whatever the
    length — the events, their records, the living — and nothing per
    row.
    """
    return _acts_from(_events(gang), viewer, alive=_alive(gang))


def latest(gang, limit=5, viewer=None):
    """The gang's last few acts, newest first.

    The whole history is not read to print five lines of it: the last
    stretch of events is, and the acts those events make up. An act whose
    events straddle the far end of that stretch would be told short,
    which is why the window is many times the number of acts asked for
    and why what comes back is taken from the near end.

    Models are named here rather than linked. This is the way through to
    the history page, which links them, and asking which of them are
    still on the roster is a query a snapshot need not spend.

    Two queries, and a third only where the stretch holds a propagated
    grant: the events, the records they name, and what those grants are
    now part of.
    """
    acts = _acts_from(_events(gang, window=SNAPSHOT_WINDOW), viewer, alive=frozenset())
    return list(reversed(acts))[:limit]


def _events(gang, window=None):
    """The gang's events, oldest first — all of them, or the last
    ``window`` of them read back to front and turned round."""
    rows = gang.ledger_events.select_related(
        "miniature",
        "actor",
        "campaign",
        "campaign_asset__asset__asset_type",
        "counterpart",
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
    sources = _comes_with_sources(events, rows)
    acts = []
    #: Where each thing's opening act landed, so an old record's grant
    #: can fold under it rather than stand beside it.
    act_of = {}
    for cluster in _clusters(events):
        _tell_cluster(cluster, rows, acts, act_of, viewer, alive, sources)
    return acts


def _comes_with_sources(events, rows):
    """For each propagated grant, the name of what it is now part of:
    the carrier its copy materialised for — the hired profile, the
    founding gang type — read fresh, as every name here is. One query,
    and only on histories that hold such a grant at all."""
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
    fetched = Assignment.with_assignables(
        Assignment.objects.filter(pk__in=wanted).select_related(
            "ledger_entry",
            "miniature",
            "miniature_root",
            "stash",
            # A pick says its kind through the question it answered.
            "chosen_for_slot__slot_type",
        )
    )
    return {row.pk: row for row in fetched}


def _name_the_rolls(events, rows):
    """Put the slot on each roll event and the roll on each pick that
    came from one — two reads, and only on histories holding a roll.

    Joined here rather than on every event and every record, because a
    roll is rare beside the run of purchases and grants, and the history
    is read whole on every page.
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
    """Consecutive events sharing a mark, as one group each.

    An unmarked event is a group of one: without the mark there is no
    saying what else was part of its act, so nothing is guessed.
    """
    grouped = []
    for e in events:
        if grouped and e.batch is not None and grouped[-1][0].batch == e.batch:
            grouped[-1].append(e)
        else:
            grouped.append([e])
    return grouped


def _tell_cluster(cluster, rows, acts, act_of, viewer, alive, sources):
    """Turn one operation's events into acts, folding what folds.

    A rider folds under the act of the thing it rode: a grant under
    what caused it, a cascaded removal, refund or sale under the thing
    that took its subtree with it. The ridden thing's event arrives in
    the same operation, written first but told last — so a rider waits
    until the cluster's acts exist, and only one whose ride never earns
    an act stands alone.

    An unmarked grant may also fold under an act clusters back, through
    its recorded cause: without the mark, its own group of one says
    nothing about whose act it was. A *marked* grant never reaches back
    — one that arrives without its cause (a choice settled later) is
    its own act, on its own day.
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
    # A campaign's types arrive on the gang in the act of joining it. They
    # have no cause of their own to ride, so they ride the joining, and
    # what they bring rides them: one act, "added the gang to Dust Falls",
    # with the types and their built-ins beneath it.
    joined = any(e.kind == Kind.JOINED_CAMPAIGN for e in cluster)
    standing = []
    waiting = []
    for e in cluster:
        row = rows.get(e.assignment_id)
        if _machinery(e, row):
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
            and e.kind == Kind.GRANTED
            and row is not None
            and row.campaign_type_id is not None
        ):
            # A campaign type only ever arrives with the joining. Told
            # apart from it — the joining outside the window being read —
            # the grant has no act to ride and draws no line, since a line
            # of its own would name a type no page names.
            if joined:
                waiting.append((e, row, _THE_JOINING))
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

    #: This cluster's act per record, so a rider folds under what its
    #: thing did *here* — never under the act that first acquired it.
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
                    act.category = "money"
            acts.append(act)
            if e.kind == Kind.JOINED_CAMPAIGN:
                local[_THE_JOINING] = act
            if row is not None:
                local[row.pk] = act
                if e.kind in {Kind.PURCHASED, Kind.ADDED, Kind.GRANTED}:
                    act_of.setdefault(row.pk, act)
            elif e.kind == Kind.ROLLED:
                act_of[_roll_key(e.pk)] = act

    # Ridden things come before their riders in the log, so a chain
    # settles in one pass: each rider finds its ride already mapped.
    # A rider's own money lands on the act it folds under — one sale,
    # one line, the whole of what moved.
    for e, row, ride in waiting:
        home = local.get(ride)
        if home is None:
            acts.append(_one_act(e, row, viewer, alive))
            continue
        # The campaign's own type wears the campaign's name and no page
        # names it, so it folds under the joining without a line of its
        # own; the shared type still says what the campaign is played as.
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
    """Propagated grants, folded per source, with nobody as the actor.

    What changed is the thing's kit, not any one model's fortunes, so
    several models' gains in one pass read as one line about the thing
    with a sub-line each — and a lone gain reads as that model's, with
    the source clause saying why it appeared. The actor stays empty:
    nobody in particular did it, and inventing a speaker would put a
    name on an act no person performed.
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


#: The key under which a cluster's joining act is filed, so the campaign
#: types granted in the same act can find it the way a rider finds its
#: ride. Never an assignment's key, which is what every other entry is.
_THE_JOINING = object()


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
    if e.kind in {Kind.REMOVED, Kind.REFUNDED, Kind.SOLD} and not row.removes:
        return row.parent_id or row.caused_by_id
    return None


def _machinery(e, row):
    """True for records a player never saw a thing for.

    A bookkeeping carrier has no name a player recognises; a weapon's
    own firing line folds into the weapon wordlessly. A *paid* firing
    line is the exception in every event it has — bought in the story,
    it must also leave in it — so the test is what its record says was
    ever priced, not what this one event moved.
    """
    if row is None:
        return False
    if e.kind == Kind.CLONED:
        return True
    if row.hidden_id is not None:
        return True
    if row.weapon_profile_id is None:
        return False
    entry = getattr(row, "ledger_entry", None)
    return entry is None or entry.list_price == 0


def _one_edit_of_what_a_model_is(standing):
    """True when one operation's records are all the owner's own edits
    of one model's subtypes and rules — the shape a section save or
    reset writes. The reason is required: choices and grants can move
    the same kinds in one breath, and those are not the owner saying
    what a model is."""
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
        spans=(
            Span("cleaned house — "),
            Span(f"{len(subs)} {models} back from Recovery"),
        ),
        subs=subs,
        category="model",
    )


def _edits_as_one(standing, viewer, alive):
    """Several same-breath edits of what one model is, as one line."""
    first, first_row = standing[0]
    model = first_row.miniature_root or first_row.miniature
    verb = "reset" if all(e.kind == Kind.REMOVED for e, _ in standing) else "changed"
    subs = []
    for e, row in standing:
        subs.append(Sub(name=_name(row), kind=_kindword(row), note=_turn(e, row)))
    return Act(
        when=first.created,
        actor=_actor(first, viewer),
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
    return Act(
        when=e.created,
        actor=_actor(e, viewer),
        spans=spans,
        credits=-e.credits_delta,
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
    """The sentence for one event, and which filter bucket it sits in.

    Spans start lowercase: the actor's name goes in front of them. The
    words are chosen so that a reader who knows nothing of how the app
    stores things reads only what happened.
    """
    thing = Span(_name(row)) if row else Span("something")
    kind = Span(_kindword(row)) if row else Span("")
    model = _model_of(e, row)
    at = _model_span(model, alive)
    identity = row is not None and (
        row.subtype_id is not None or row.rule_id is not None
    )
    category = (
        "money"
        if e.kind in MONEY or e.credits_delta
        else "model"
        if e.kind in PERSONAL or identity or e.kind == Kind.TALLIED
        else "kit"
    )

    if _about_a_holding(e):
        return _tell_holding(e), "gang"

    match e.kind:
        case Kind.PURCHASED:
            if row is not None and row.profile_id is not None:
                return (Span("hired "), at, Span(f", a {_name(row)}")), "money"
            if identity:
                return (
                    Span("bought the "),
                    kind,
                    Span(" "),
                    thing,
                    *_for(model, at),
                ), "money"
            return (Span("bought "), thing, *_for(model, at)), "money"
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
            return (
                Span("gained "),
                thing,
                *_for(model, at, "on"),
                Span(rolled),
            ), category
        case Kind.GRANTED:
            # Only reached when what caused it is not in the story.
            return (Span("gained "), thing, *_for(model, at, "on")), category
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
            return (Span("removed "), thing, *_for(model, at, "from")), category
        case Kind.REFUNDED:
            return (Span("returned "), thing, Span(" for a refund")), "money"
        case Kind.SOLD:
            return (Span("sold "), thing), "money"
        case Kind.REPRICED:
            return (Span("the price of "), thing, Span(" changed")), "money"
        case Kind.AMENDED:
            return (Span("changed "), thing), "money"
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
                return (Span(f"paid {figure} to {other}"), *because), "money"
            return (Span(f"received {figure} from {other}"), *because), "money"
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
            # The arbitrator is the actor, so the verb is theirs: a gang
            # does not join itself, and "joined" would read as the person who
            # did the adding joining. Which gang goes unsaid — a gang's own
            # history is already about it, and a campaign's log says whose
            # every act was beside the sentence.
            where = e.campaign.name if e.campaign else "a campaign"
            if e.kind == Kind.JOINED_CAMPAIGN:
                return (Span(f"added the gang to {where}"),), "gang"
            return (Span(f"took the gang out of {where}"),), "gang"
        case Kind.BUDGET_SET:
            _, _, now = e.note.rpartition(" → ")
            if now == NO_CEILING:
                return (Span("lifted the budget — the gang spends freely"),), "money"
            if now:
                return (Span(f"set the budget to {now}"),), "money"
            return (Span("changed the budget"),), "money"
        # A trip to the trading post wrote these before it was an action
        # of its own. Nothing writes them now; the sentences stay so that
        # a gang's older history still reads. Finishing says "completed",
        # the word an action's own ending uses, so a gang that visited
        # either side of the change reads as one story.
        case Kind.TRADE_POINTS_SET if e.note == "closed":
            return (Span("completed the Visit Trading Post action"),), "money"
        case Kind.TRADE_POINTS_SET:
            brought = e.note
            if brought == "1":
                return (Span("visited the Trading Post with 1 Trade Point"),), "money"
            if brought:
                return (
                    Span(f"visited the Trading Post with {brought} Trade Points"),
                ), "money"
            return (Span("visited the Trading Post"),), "money"
        case Kind.ACTION_OPENED:
            named, brought = read_note(e.note)
            if not named:
                return (Span("started an action"),), "gang"
            if brought is None:
                return (Span(f"started the {named} action"),), "gang"
            return (
                Span(f"started the {named} action with {_points(brought)}"),
            ), "gang"
        case Kind.ACTION_CLOSED:
            named, left = read_note(e.note)
            if not named:
                return (Span("completed an action"),), "gang"
            if left is None or left <= 0:
                return (Span(f"completed the {named} action"),), "gang"
            return (
                Span(f"completed the {named} action, discarding {_points(left, True)}"),
            ), "gang"
        case Kind.VISITED_TRADING_POST:
            # What raised their figure rides the note, so the line says
            # what they added rather than what they happen to be now. A
            # bare figure lands there where several things raised it, and
            # "sent Rasp as 3" is no sentence — the line then says only
            # that they went.
            went_as = f" as {e.note}" if e.note and not e.note.isdigit() else ""
            return (
                Span("sent "),
                at,
                Span(f"{went_as} to the trading post"),
            ), "money"
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


def _about_a_holding(e):
    """Whether this record is a campaign's asset coming to the gang or
    leaving it. The two kinds are written for nothing else."""
    return e.kind in HOLDING


def _holding_name(e):
    """The asset an event is about, linked to the campaign's assets while
    it still stands. One removed from the campaign since is named from the
    note, which kept the name for exactly this: the line still says what
    the gang gained or lost."""
    campaign_asset = e.campaign_asset
    if campaign_asset is None:
        return Span(e.note or "an asset")
    return Span(
        str(campaign_asset),
        reverse("n26-campaign", args=[campaign_asset.campaign_id]) + "#assets",
    )


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
    from n26.core.models import Action

    try:
        return Action.Kind(note).label
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


def _for(model, at, word="for"):
    """(" for ", {model}) with the name linked, or nothing where the
    act has no model."""
    if model is None:
        return ()
    return (Span(f" {word} "), at)


#: Kinds whose note is a record for the code rather than words for a
#: reader — the figure a visit brought, the word that says one closed,
#: the rank a fighter went as, what a tally moved and why. The sentence
#: has already said all of them, and printing the note under it puts
#: bookkeeping on the page.
_NOTE_IS_MACHINERY = {
    Kind.CLONED,
    Kind.STATUS_SET,
    Kind.TRANSFERRED,
    Kind.TRADE_POINTS_SET,
    Kind.VISITED_TRADING_POST,
    Kind.TALLIED,
    Kind.ACTION_OPENED,
    Kind.ACTION_CLOSED,
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


def _name(row):
    thing = row.assignable if row else None
    return str(thing) if thing is not None else "something"


def _kindword(row):
    """What sort of thing this is, in the library's own word — empty
    for the kinds a player's page never names.

    A pick is one of those: "pickable" is plumbing, and no player has
    ever seen the word. What they know it as is the sort of question it
    answered — a Gang Legacy, a Path — so the slot's type says it
    instead. The type rather than the slot's own label, because a label
    names one question among several ("Skill Tree 2") where a kind word
    names what sort of thing arrived — and without this a story that
    read "Sniper, specialisation" before that question moved onto a slot
    would afterwards read only "Sniper".
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


def campaign_history(campaign, viewer=None, limit=None):
    """Every act in this campaign's history, oldest first.

    The same shape a gang's history has, so a page that can draw one can draw
    the other. Acts come from more than one place — the campaign's own, and
    what the gangs in it did while they were in it — so each source is read on
    its own and the results merged in time order. Merging is what keeps the
    log one story rather than several lists side by side.

    ``limit`` keeps the most recent acts and drops the rest. Each source is
    asked for its own newest that many, and the merge cuts again, so the
    answer is the newest across all of them however they are spread.
    """
    dated = [
        *_campaign_own_acts(campaign, viewer, limit),
        *_gang_acts_in_campaign(campaign, viewer, limit),
    ]
    dated.sort(key=lambda row: row[0])
    if limit is not None:
        dated = dated[-limit:]
    return [act for _, act in dated]


def campaign_history_size(campaign):
    """How many acts the history holds, without building any of them.

    Counted by record, less the records that never stand as acts of their
    own: a grant riding what caused it, and a campaign type riding the
    joining that put it on the gang. What is left is close to the number
    of lines the full history draws, which is what a reader comparing
    "N earlier acts not shown" against the page expects it to mean.
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
        + campaign.gang_events.exclude(riders)
        .exclude(handed_over)
        .exclude(kind=Kind.CLONED, assignment__isnull=False)
        .count()
    )


def _campaign_own_acts(campaign, viewer, limit=None):
    """What the arbitrator changed about the campaign itself, one act each."""
    events = campaign.events.select_related("actor", "battle", "about_user")
    # Newest first while the database is doing the cutting, so a limit takes
    # the recent end; the caller sorts the merged result back into order.
    events = (
        events.order_by("-created", "-id")[:limit]
        if limit is not None
        else events.order_by("created", "id")
    )
    for e in events:
        yield (e.created, str(e.pk)), _one_campaign_act(e, viewer)


def _gang_acts_in_campaign(campaign, viewer, limit=None):
    """What the gangs in this campaign did while they were in it.

    Their own ledger events, which name the campaign because the operation
    that wrote them read the gang's membership. One record, two readers: the
    same act appears here and in the gang's own history, and neither is a copy
    of the other — which is why they are told by the same machinery, folding
    what folds, so a hire is one line with its kit beneath it in both places.

    Acts are gathered a gang at a time. A mark belongs to one operation and an
    operation is one gang's, so nothing clusters across a boundary anyway, and
    grouping first keeps one gang's riders from folding under another's act.
    """
    from n26.core.models import LedgerEvent, Miniature

    events = (
        LedgerEvent.objects.filter(campaign=campaign)
        # A clone's assignment-level openings are ledger machinery. Its one
        # standalone event already holds the visible act and its totals, so
        # letting the openings consume a page would make one large clone hide
        # the acts immediately before it.
        .exclude(kind=LedgerEvent.Kind.CLONED, assignment__isnull=False)
        .select_related(
            "miniature",
            "actor",
            "gang",
            "campaign",
            "campaign_asset__asset__asset_type",
            "counterpart",
        )
    )
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
    """The campaign's assets moving between its gangs, one act each.

    "Old Ruins went to Ash Vipers" for an asset assigned, "Ash Vipers lost
    Old Ruins" for one unassigned, and "Old Ruins went from Ash Vipers to
    Hammerfall" for one handed over — the LOST and the GAINED that share a
    mark, told once. Nobody is named as the actor: the sentence is about
    what the asset did, and who moved it is in each gang's own history.
    ``events`` are oldest first, and the acts come out the same way.
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
            Act(when=first.created, actor="", spans=spans, category="gang"),
        )


def _gang_named(e):
    return e.gang.name if e.gang_id else "a gang"


def _one_campaign_act(e, viewer):
    spans, category = _tell_campaign(e)
    return Act(
        when=e.created,
        actor=_actor(e, viewer),
        spans=spans,
        category=category,
    )


def _tell_campaign(e):
    """One campaign event as a sentence, lowercase because the actor's name
    comes first. Money is never mentioned: nothing here moves any."""
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
        case kinds.SUMMARY_EDITED:
            return (Span("edited the campaign's summary"),), "campaign"
        case kinds.ARCHIVED:
            return (Span("archived the campaign"),), "campaign"
        case (
            kinds.INVITED
            | kinds.INVITE_ACCEPTED
            | kinds.INVITE_DECLINED
            | kinds.PLAYER_REMOVED
        ):
            # An answer is the invited person's own act, so the actor's name
            # already leads the sentence and naming them again would say it
            # twice. Asking and removing are the arbitrator's, and there the
            # sentence has to say who it was about.
            who = e.about_user.username if e.about_user_id else "somebody"
            match e.kind:
                case kinds.INVITED:
                    return (Span(f"invited {who}"),), "campaign"
                case kinds.INVITE_ACCEPTED:
                    return (Span("accepted the invitation"),), "campaign"
                case kinds.INVITE_DECLINED:
                    return (Span("declined the invitation"),), "campaign"
            return (Span(f"removed {who} from the campaign"),), "campaign"
        case kinds.BATTLE_RECORDED:
            when = e.battle.date if e.battle else None
            if when:
                return (Span(f"recorded a battle fought on {when:%-d %B}"),), "campaign"
            return (Span("recorded a battle"),), "campaign"
        case kinds.BATTLE_REMOVED:
            if e.note:
                return (Span(f"removed the battle of {e.note}"),), "campaign"
            return (Span("removed a battle"),), "campaign"
        case kinds.ASSET_ADDED:
            # The note is the asset's name at the time. One removed since is
            # still named, which is what a log is for.
            what = f"the asset {e.note}" if e.note else "an asset"
            return (Span(f"added {what}"),), "campaign"
        case kinds.ASSET_REMOVED:
            what = f"the asset {e.note}" if e.note else "an asset"
            return (Span(f"removed {what}"),), "campaign"
        case kinds.ASSET_TYPE_ADDED:
            what = f"the asset type {e.note}" if e.note else "an asset type"
            return (Span(f"added {what}"),), "campaign"
        case kinds.ASSET_CREATED:
            what = f"the asset {e.note}" if e.note else "an asset"
            return (Span(f"created {what}"),), "campaign"
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
    return (Span("changed the campaign"),), "campaign"
