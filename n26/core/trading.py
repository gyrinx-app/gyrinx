"""The Visit Trading Post action — who performs it, and what it adds.

A gang's Trade Points are not a standing figure. They arrive when a
fighter performs the action, are spent at the post, and what is left is
lost when the action is done; the rules also shut the post entirely to a
gang where nobody performed it. The edition keeps that as an
``n26.core.models.Action`` row, open from the click that started the
visit to the click that ended it, carrying what the visit brought. What
it has spent is the purchases pointing back at it
(``n26.core.reconcile.trade_points_spent``), so the story of a visit
stays what the ledger says, which is already how everything else in this
edition is described.

        Two ranks add Trade Points, and only they are offered: picking a
        fighter who adds none is a choice with no consequence, and the form
        asks one question rather than listing a roster to say no to most of it.
Equipping is the other half and has no such limit — anything the gang
bought is handed to whoever it is for.

The ranks are read off what each model *holds* — the subtypes on their
card — rather than off the entry they were hired as, so a fighter
promoted into the rank counts and one who has lost it does not.
"""

from dataclasses import dataclass

#: What each rank adds to a post, by the subtype's own name. The book
#: names two; every other model adds nothing and may still go.
TRADE_POINTS_FOR_RANK = {"Leader": 2, "Champion": 1}


@dataclass(frozen=True)
class Visitor:
    """One model who could perform the action, and what they would add."""

    miniature: object
    rank: str
    trade_points: int
    visiting: bool = False

    @property
    def key(self):
        return str(self.miniature.pk)


def brings(rank):
    """What a model of this rank adds to the gang's Trade Points."""
    return TRADE_POINTS_FOR_RANK.get(rank, 0)


def visitors(gang, going=None):
    """The fighters who could add Trade Points, in rank order then by name.

    ``going`` is the set of model ids the owner has ticked; ``None``
    opens with all of them ticked, which is what a post-cycle almost
    always wants. The form itself starts with none ticked, and passes
    an empty set.

    A model holding both ranks adds the better of the two: the same
    fighter cannot perform the action twice.

    Two queries — the roster, then the ranks anybody holds. Removals are
    read with them: an assignment with ``removes`` set is machinery
    rather than a line, so anything reading assignments straight from
    the database has to cancel the pair itself, or a Leader an owner
    took away goes on adding two points.
    """
    from n26.core.models import Assignment
    from n26.core.render import roster

    members = roster(gang)
    held = Assignment.objects.filter(
        gang_root=gang,
        archived=False,
        subtype__name__in=TRADE_POINTS_FOR_RANK,
        miniature_root__membership__archived=False,
    ).values_list("miniature_root_id", "subtype__name", "removes")
    gone = {(model, rank) for model, rank, removes in held if removes}
    ranks = {}
    for model, rank, removes in held:
        if removes or (model, rank) in gone:
            continue
        if brings(rank) > brings(ranks.get(model, "")):
            ranks[model] = rank
    return [
        Visitor(
            miniature=member,
            rank=ranks[member.pk],
            trade_points=brings(ranks[member.pk]),
            visiting=going is None or str(member.pk) in going,
        )
        for member in sorted(
            (member for member in members if member.pk in ranks),
            key=lambda m: (-brings(ranks[m.pk]), m.name),
        )
    ]


def minted(going):
    """What a set of visitors adds between them."""
    return sum(visitor.trade_points for visitor in going if visitor.visiting)


def as_offer(going, label="Who is visiting"):
    """The visitors as a list of things to tick, under their ranks.

    ``ChoiceOffer`` is the shape the edition already ticks lists in, and
    ``<c-n26.tick-list>`` draws it with plain checkboxes and no script.
    The headings are the ranks, which is what a heading is for here: what
    a model adds follows from the rank they are filed under, so the
    figure is said once per group rather than once per model.

    The better rank leads.
    """
    from n26.core.render import ChoiceOffer, Choosable, ChoosableGroup

    ranks = {}
    for visitor in going:
        ranks.setdefault(visitor.rank, []).append(visitor)
    ordered = sorted(ranks.items(), key=lambda pair: -brings(pair[0]))
    return ChoiceOffer(
        label=label,
        groups=[
            ChoosableGroup(
                name=rank,
                caption=_caption(brings(rank)),
                options=[
                    Choosable(
                        key=visitor.key,
                        name=visitor.miniature.name,
                        thing=visitor.miniature,
                        is_current=visitor.visiting,
                    )
                    for visitor in members
                ],
            )
            for rank, members in ordered
        ],
    )


def _caption(points):
    if not points:
        return "no Trade Points"
    return f"{points} Trade Point{'' if points == 1 else 's'} each"


@dataclass(frozen=True)
class Contributor:
    """One fighter who performed the action, as the receipt names them.

    ``miniature`` rides along because the receipt is where an owner goes
    next: having sent a fighter to the post, the thing they want is that
    fighter's own equip screen. ``on_roster`` is False for one who has
    since left — the record of their visit stands, but there is no page
    left to send anybody to.
    """

    name: str
    rank: str
    trade_points: int
    miniature: object = None
    on_roster: bool = True


@dataclass(frozen=True)
class Receipt:
    """An open Visit Trading Post action, as the figures it is read by.

    Built for the screen rather than stored: what a visit added is the
    figure on the action, what it has spent is the ledger's answer, and
    who went is the events the opening act wrote. Nothing here is a
    second copy of any of them.
    """

    available: int
    spent: int
    remaining: int
    contributors: tuple[Contributor, ...] = ()

    @property
    def facts(self):
        """The visit as a tally: what it added, what has gone, what is
        left. Drawn by ``<c-n26.tally>``, which the overspend
        confirmation draws too — one arithmetic, one shape."""
        from n26.core.confirm import Fact

        return (
            Fact("Available", str(self.available), sub=self.summary),
            Fact("Spent", str(self.spent)),
            Fact("Remaining", str(self.remaining), ruled=True, strong=True),
        )

    @property
    def summary(self):
        """The contributors as one line — "Leader, Champion × 2".

        Ranks rather than names, because this sits against the figure
        they add up to and answers where it came from. Who went is drawn
        beside it, by name, since that is the different question.
        """
        counts = {}
        for one in self.contributors:
            counts[one.rank] = counts.get(one.rank, 0) + 1
        return ", ".join(
            rank if count == 1 else f"{rank} × {count}"
            for rank, count in sorted(counts.items(), key=lambda p: -brings(p[0]))
        )


def _still_here(miniature):
    """Whether this model is on the roster, so a link to them leads
    somewhere."""
    if miniature is None:
        return False
    membership = getattr(miniature, "membership", None)
    return membership is not None and not membership.archived


def receipt_for(gang):
    """The open visit's figures, or None where the post is shut.

    Read off the action the gang has open: what it brought is on the row,
    and who performed it is the batch the opening event stamped on
    everything that act wrote.

    One query beyond what the figures already cost: who went.
    """
    from n26.core.models import LedgerEvent

    visit = gang.open_visit
    if visit is None:
        return None
    available = visit.trade_points or 0
    opened = visit.opened
    went = []
    if opened is not None and opened.batch is not None:
        went = [
            Contributor(
                name=event.miniature.name if event.miniature else "",
                rank=event.note,
                trade_points=brings(event.note),
                miniature=event.miniature,
                on_roster=_still_here(event.miniature),
            )
            for event in LedgerEvent.objects.filter(
                gang=gang,
                kind=LedgerEvent.Kind.VISITED_TRADING_POST,
                batch=opened.batch,
            ).select_related("miniature__membership")
        ]
    spent = gang.trade_points_spent
    return Receipt(
        available=available,
        spent=spent,
        remaining=available - spent,
        contributors=tuple(went),
    )
