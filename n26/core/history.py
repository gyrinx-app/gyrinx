"""The gang's history, told plainly.

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

from n26.core.models import Assignment, LedgerEvent

Kind = LedgerEvent.Kind

#: The kinds that concern money. "Amended" is here because re-choosing
#: how a thing is built can change what it charges.
MONEY = {Kind.PURCHASED, Kind.REFUNDED, Kind.SOLD, Kind.REPRICED, Kind.AMENDED}

#: The kinds that are always about the model itself rather than its kit.
PERSONAL = {
    Kind.TOOK_AWAY,
    Kind.RENAMED,
    Kind.NOTED,
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


@dataclass
class Act:
    """One thing done to the gang, in the player's words.

    ``credits`` and ``rating`` carry the player's reading of the money:
    negative credits left the pot, positive came back. ``actor`` is the
    subject the sentence starts with, or empty where nobody in
    particular did it. ``category`` and ``miniature_pk`` exist for the
    page's filters; ``search`` is every word worth matching against.
    """

    when: object
    actor: str
    spans: tuple[Span, ...]
    credits: int = 0
    rating: int = 0
    note: str = ""
    subs: list[Sub] = field(default_factory=list)
    category: str = "kit"
    miniature_pk: str = ""
    miniature_name: str = ""

    @property
    def search(self):
        words = [span.text for span in self.spans]
        words += [sub.name for sub in self.subs]
        words.append(self.note)
        return " ".join(words).casefold()


def build(gang, viewer=None):
    """Every act in this gang's history, oldest first.

    ``viewer`` names who is reading: their own acts say "You", anyone
    else's say the actor's name. Three queries whatever the length —
    the events, their records, and nothing per row.
    """
    events = list(
        gang.ledger_events.select_related("miniature", "actor").order_by(
            "created", "id"
        )
    )
    rows = _rows_for(events)
    acts = []
    #: Where each thing's opening act landed, so what it caused can fold
    #: under it rather than stand beside it.
    act_of = {}
    for cluster in _clusters(events):
        _tell_cluster(cluster, rows, acts, act_of, viewer)
    return acts


def _rows_for(events):
    """The assignments the events name, resolved to their things."""
    wanted = {e.assignment_id for e in events if e.assignment_id}
    fetched = Assignment.with_assignables(
        Assignment.objects.filter(pk__in=wanted).select_related(
            "ledger_entry", "miniature", "miniature_root", "stash"
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


def _tell_cluster(cluster, rows, acts, act_of, viewer):
    """Turn one operation's events into acts, folding what folds.

    A grant folds under the act of what caused it. Its cause usually
    arrives in the same operation, written first but told last — so a
    grant whose cause is here waits until the cluster's acts exist,
    and only a grant whose cause never earns an act stands alone.
    """
    here = {e.assignment_id for e in cluster if e.assignment_id is not None}
    standing = []
    waiting = []
    for e in cluster:
        row = rows.get(e.assignment_id)
        if _machinery(e, row):
            continue
        if e.kind == Kind.GRANTED and row is not None:
            home = act_of.get(row.caused_by_id)
            if home is not None:
                home.subs.append(Sub(name=_name(row), kind=_kindword(row)))
                act_of.setdefault(row.pk, home)
                continue
            if row.caused_by_id in here:
                waiting.append((e, row))
                continue
        standing.append((e, row))

    if _one_edit_of_what_a_model_is(standing, rows):
        act = _edits_as_one(standing, rows, viewer)
        acts.append(act)
        for _, row in standing:
            if row is not None:
                act_of.setdefault(row.pk, act)
    else:
        for e, row in standing:
            act = _one_act(e, row, viewer)
            acts.append(act)
            if row is not None and e.kind in {
                Kind.PURCHASED,
                Kind.ADDED,
                Kind.GRANTED,
            }:
                act_of.setdefault(row.pk, act)

    # Causes come before their effects in the log, so a chain of grants
    # settles in one pass: each finds its cause's act already mapped.
    for e, row in waiting:
        home = act_of.get(row.caused_by_id)
        if home is None:
            acts.append(_one_act(e, row, viewer))
            continue
        home.subs.append(Sub(name=_name(row), kind=_kindword(row)))
        act_of.setdefault(row.pk, home)


def _machinery(e, row):
    """True for records a player never saw a thing for.

    A bookkeeping entry has no name a player recognises; a weapon's
    firing line is the weapon's own and folds into it wordlessly. Only
    the free kind is silent — money is always shown, whatever it
    bought.
    """
    if row is None:
        return False
    if row.hidden_id is not None:
        return True
    return row.weapon_profile_id is not None and e.credits_delta == 0


def _one_edit_of_what_a_model_is(standing, rows):
    """True when one operation's records are all edits of one model's
    subtypes and rules — the shape a section save or reset writes."""
    if len(standing) < 2:
        return False
    models = set()
    for e, row in standing:
        if row is None or (row.subtype_id is None and row.rule_id is None):
            return False
        if e.kind not in {Kind.ADDED, Kind.TOOK_AWAY, Kind.REMOVED}:
            return False
        models.add(row.miniature_root_id or row.miniature_id)
    return len(models) == 1


def _edits_as_one(standing, rows, viewer):
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
        spans=(Span(f"{verb} what "), _model_span(model), Span(" is")),
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


def _one_act(e, row, viewer):
    spans, category = _tell(e, row)
    model = _model_of(e, row)
    return Act(
        when=e.created,
        actor=_actor(e, viewer),
        spans=spans,
        credits=-e.credits_delta,
        rating=e.rating_delta,
        note=_shown_note(e),
        category=category,
        miniature_pk=str(model.pk) if model else "",
        miniature_name=str(model) if model else "",
    )


def _tell(e, row):
    """The sentence for one event, and which filter bucket it sits in.

    Spans start lowercase: the actor's name goes in front of them. The
    words are chosen so that a reader who knows nothing of how the app
    stores things reads only what happened.
    """
    thing = Span(_name(row)) if row else Span("something")
    kind = Span(_kindword(row)) if row else Span("")
    model = _model_of(e, row)
    at = _model_span(model)
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
                return (Span("created the gang, a "), thing, Span(" gang")), "kit"
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
            if was:
                return (Span(f"renamed {was} to "), Span(now, at.href)), "model"
            return (Span("renamed "), at), "model"
        case Kind.NOTED:
            return (Span("edited "), at, Span("'s notes")), "model"
        case Kind.STAT_SET:
            said, _, now = e.note.rpartition(" → ")
            stat, _, was = said.rpartition(" ")
            if stat:
                return (Span("set "), at, Span(f"'s {stat} to {now}")), "model"
            return (Span("set a characteristic of "), at), "model"
        case Kind.STAT_CLEARED:
            said = e.note.split(" → ")[0]
            stat = said.rpartition(" ")[0] or "a characteristic"
            return (Span("cleared "), at, Span(f"'s {stat}")), "model"
    return (Span(e.get_kind_display().casefold()),), category


def _for(model, at, word="for"):
    """(" for ", {model}) with the name linked, or nothing where the
    act has no model."""
    if model is None:
        return ()
    return (Span(f" {word} "), at)


def _shown_note(e):
    """The note, where it is the player's words rather than a record the
    sentence already told."""
    if e.kind in {Kind.RENAMED, Kind.STAT_SET, Kind.STAT_CLEARED}:
        return e.note
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
    """What sort of thing this is, in the library's own word."""
    thing = row.assignable if row else None
    if thing is None:
        return ""
    return str(type(thing)._meta.verbose_name)


def _model_of(e, row):
    if e.miniature is not None:
        return e.miniature
    if row is not None:
        return row.miniature_root or row.miniature
    return None


def _model_span(model):
    if model is None:
        return Span("")
    return Span(str(model), reverse("n26-equip", args=[model.pk]))
