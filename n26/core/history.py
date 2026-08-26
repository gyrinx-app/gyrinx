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
from n26.core.effects import kind_of
from n26.core.models import Assignment, CampaignEvent, LedgerEvent, Reason

Kind = LedgerEvent.Kind

#: The kinds that concern money. "Amended" is here because re-choosing
#: how a thing is built can change what it charges.
MONEY = {Kind.PURCHASED, Kind.REFUNDED, Kind.SOLD, Kind.REPRICED, Kind.AMENDED}

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


def build(gang, viewer=None):
    """Every act in this gang's history, oldest first.

    ``viewer`` names who is reading: their own acts say "You", anyone
    else's say the actor's name. A fixed number of queries whatever the
    length — the events, their records, the living — and nothing per
    row.
    """
    from n26.core.models import Miniature

    events = list(
        gang.ledger_events.select_related("miniature", "actor", "campaign").order_by(
            "created", "id"
        )
    )
    rows = _rows_for(events)
    # The history keeps the dead, but only the living have a page to
    # link to — a departed model's name reads as words.
    alive = set(
        Miniature.objects.filter(
            membership__gang=gang, membership__archived=False
        ).values_list("pk", flat=True)
    )
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
    here = {e.assignment_id for e in cluster if e.assignment_id is not None}
    standing = []
    waiting = []
    for e in cluster:
        row = rows.get(e.assignment_id)
        if _machinery(e, row):
            continue
        ride = _rides(e, row)
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
    if _one_edit_of_what_a_model_is(standing):
        act = _edits_as_one(standing, viewer, alive)
        acts.append(act)
        for _, row in standing:
            if row is not None:
                local[row.pk] = act
                act_of.setdefault(row.pk, act)
    else:
        for e, row in standing:
            act = _one_act(e, row, viewer, alive)
            acts.append(act)
            if row is not None:
                local[row.pk] = act
                if e.kind in {Kind.PURCHASED, Kind.ADDED, Kind.GRANTED}:
                    act_of.setdefault(row.pk, act)

    # Ridden things come before their riders in the log, so a chain
    # settles in one pass: each rider finds its ride already mapped.
    # A rider's own money lands on the act it folds under — one sale,
    # one line, the whole of what moved.
    for e, row, ride in waiting:
        home = local.get(ride)
        if home is None:
            acts.append(_one_act(e, row, viewer, alive))
            continue
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
        case Kind.GRANTED:
            # Only reached when what caused it is not in the story.
            return (Span("gained "), thing, *_for(model, at, "on")), category
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
            return (Span("changed "), thing, *_for(model, at, "on")), "model"
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
        case Kind.TRADE_POINTS_SET if e.note == "closed":
            return (Span("finished the Visit Trading Post action"),), "money"
        case Kind.TRADE_POINTS_SET:
            brought = e.note
            if brought == "1":
                return (Span("visited the trading post with 1 Trade Point"),), "money"
            if brought:
                return (
                    Span(f"visited the trading post with {brought} Trade Points"),
                ), "money"
            return (Span("visited the trading post"),), "money"
        case Kind.VISITED_TRADING_POST:
            # The rank they went as rides the note, so the line says what
            # they brought rather than what they happen to be now.
            went_as = f" as {e.note}" if e.note else ""
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


def _for(model, at, word="for"):
    """(" for ", {model}) with the name linked, or nothing where the
    act has no model."""
    if model is None:
        return ()
    return (Span(f" {word} "), at)


#: Kinds whose note is a record for the code rather than words for a
#: reader — the figure a visit brought, the word that says one closed,
#: the rank a fighter went as. The sentence has already said all three,
#: and printing the note under it puts bookkeeping on the page.
_NOTE_IS_MACHINERY = {Kind.TRADE_POINTS_SET, Kind.VISITED_TRADING_POST}


def _shown_note(e):
    """The note, where it is the player's words rather than a record the
    sentence already told."""
    if e.kind in {Kind.RENAMED, Kind.STAT_SET, Kind.STAT_CLEARED}:
        return e.note
    if e.kind in _NOTE_IS_MACHINERY:
        return ""
    if e.note == "reset":
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
    """How many acts the history holds, without building any of them."""
    return campaign.events.count() + campaign.gang_events.count()


def _campaign_own_acts(campaign, viewer, limit=None):
    """What the arbitrator changed about the campaign itself, one act each."""
    events = campaign.events.select_related("actor")
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

    events = LedgerEvent.objects.filter(campaign=campaign).select_related(
        "miniature", "actor", "gang", "campaign"
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

    rows = _rows_for(events)
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
            return (Span("set the campaign up"),), "campaign"
        case kinds.RENAMED:
            was, _, now = e.note.rpartition(" → ")
            if was:
                return (Span(f"renamed the campaign {was} to {now}"),), "campaign"
            return (Span("renamed the campaign"),), "campaign"
        case kinds.BUDGET_SET:
            _, _, now = e.note.rpartition(" → ")
            if now == NO_CEILING:
                return (
                    Span(
                        "removed the gang budget — gangs enter at whatever they are worth"
                    ),
                ), "campaign"
            if now:
                return (Span(f"set the gang budget to {now}¢"),), "campaign"
            return (Span("changed the gang budget"),), "campaign"
        case kinds.SUMMARY_EDITED:
            return (Span("edited the campaign's summary"),), "campaign"
        case kinds.ARCHIVED:
            return (Span("archived the campaign"),), "campaign"
    return (Span("changed the campaign"),), "campaign"
