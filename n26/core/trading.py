"""The Visit Trading Post action — who performs it, and what it adds.

A gang's Trade Points are not a standing figure. They arrive when a
fighter performs the action, are spent at the post, and what is left is
lost when the action is done; the rules also shut the post entirely to a
gang where nobody performed it. The edition keeps that as an amount on
the gang — null while no visit is open — plus the event the spending is
measured from (``n26.core.reconcile.trade_points_spent``). There is no
visit table: what a visit *is* is the events one act wrote, which is
already how the ledger describes everything else.

Only the models who add something are offered: picking a fighter who
adds none is a choice with no consequence, and the form asks one
question rather than listing a roster to say no to most of it. Equipping
is the other half and has no such limit — anything the gang bought is
handed to whoever it is for.

What a model adds is a **counter reading**, not a rank this module
knows. The library holds a counter, ``Trading Post visit contribution``,
that no card draws, and a modifier on each rank raises it — 2 on Leader,
1 on Champion. So the figure is read off the computed card, which means a
fighter promoted into a rank adds it, one who has lost the rank adds
nothing, and changing what a rank adds is an authoring edit. A library
with no such counter offers nobody, and the typed figure is then the only
way to open a visit.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Visitor:
    """One model who could perform the action, and what they would add.

    ``rank`` is what the card says raised the figure — the subtype's own
    name, where one thing raised it. Where several did, it is the figure
    itself, because no single name would be true. It is what the visit
    records against the model.
    """

    miniature: object
    rank: str
    trade_points: int
    visiting: bool = False

    @property
    def key(self):
        return str(self.miniature.pk)


def _readings(gang, counter):
    """Each model's reading of this counter, and what raised it, by id.

    The gang's cards are built and computed the way the gang sheet builds
    and computes them — the gang's own card first, since what it holds by
    grant is dealt onto every member's — so a modifier the gang carries
    reaches the ranks exactly as it does everywhere else.

    A fixed number of queries however many models are on the roster:
    ``compute`` touches the database not at all.
    """
    from n26.core.card import build_gang_card, build_modifier_index
    from n26.core.effects import compute, compute_gang, counter_readings

    # No statlines: nothing here draws a card, and pulling each
    # profile's characteristics along would be several queries for
    # figures this never reads.
    card = build_gang_card(gang, with_statlines=False)
    index = build_modifier_index(
        [
            node.assignable
            for member in card.members.values()
            for node in member.all_nodes()
        ]
        + [node.assignable for node in card.all_nodes()]
    )
    compute_gang(card, index)
    readings = {}
    for miniature_id, member in card.members.items():
        computed = compute(member, index)
        value = next(
            (
                reading.value
                for reading in counter_readings(member, computed)
                if reading.thing.pk == counter.pk
            ),
            0,
        )
        readings[miniature_id] = (value, _raised_by(computed, counter) or str(value))
    return readings


def _raised_by(computed, counter):
    """What the card names as raising this counter, where one thing did.

    Empty where several did, or where the figure was tallied rather than
    contributed: the visit records one name against the model, and a
    joined-up list of them would not be one.
    """
    named = {
        contribution.source
        for contribution in computed.counter_contributions
        if contribution.counter.pk == counter.pk
    }
    return named.pop() if len(named) == 1 else ""


def visitors(gang, going=None, members=None):
    """The fighters who could add Trade Points, biggest figure first
    then by name.

    ``going`` is the set of model ids the owner has ticked; ``None``
    opens with all of them ticked, which is what a post-cycle almost
    always wants. The form itself starts with none ticked, and passes
    an empty set.

    ``members`` is the gang's roster where the caller already holds it.
    The page draws every fighter as well as the ones offered, and reading
    the roster twice is a query for an answer already in hand.

    A model holding both ranks adds the better of the two, because the
    same fighter cannot perform the action twice. That is content, not
    arithmetic here: the modifier on the lesser rank is scoped away from
    models holding the better one, so the two never add up.
    """
    from n26.core.render import roster
    from n26.library.standard_content import visit_contribution_counter

    counter = visit_contribution_counter()
    if counter is None:
        return []
    readings = _readings(gang, counter)
    offered = []
    for member in roster(gang) if members is None else members:
        trade_points, raised_by = readings.get(member.pk, (0, ""))
        if trade_points <= 0:
            continue
        offered.append(
            Visitor(
                miniature=member,
                rank=raised_by,
                trade_points=trade_points,
                visiting=going is None or str(member.pk) in going,
            )
        )
    offered.sort(key=lambda one: (-one.trade_points, one.miniature.name))
    return offered


def minted(going):
    """What a set of visitors adds between them."""
    return sum(visitor.trade_points for visitor in going if visitor.visiting)


def as_offer(going, label="Who is visiting"):
    """The visitors as a list of things to tick, under what they add.

    ``ChoiceOffer`` is the shape the edition already ticks lists in, and
    ``<c-n26.tick-list>`` draws it with plain checkboxes and no script.
    The headings are the figures, which is what a heading is for here:
    what a model adds follows from the group they are filed under, so the
    figure is said once per group rather than once per model.

    Grouped by the figure and not by the rank, because the rank is not
    what this knows — content decides what raises a model's contribution,
    and two things may raise it by the same amount.

    The bigger figure leads.
    """
    from n26.core.render import ChoiceOffer, Choosable, ChoosableGroup

    groups = {}
    for visitor in going:
        groups.setdefault(visitor.trade_points, []).append(visitor)
    return ChoiceOffer(
        label=label,
        groups=[
            ChoosableGroup(
                name=_adds_each(trade_points),
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
            for trade_points, members in sorted(
                groups.items(), key=lambda pair: -pair[0]
            )
        ],
    )


def _adds_each(trade_points):
    """A group's heading: what every model under it adds."""
    return f"{trade_points} Trade Point{'' if trade_points == 1 else 's'} each"


@dataclass(frozen=True)
class Contributor:
    """One fighter who performed the action, as the receipt names them.

    ``rank`` is what the visit recorded against them — the name of what
    raised their figure at the time, so a fighter who has since lost the
    rank is still reported as having gone as it.

    ``miniature`` rides along because the receipt is where an owner goes
    next: having sent a fighter to the post, the thing they want is that
    fighter's own equip screen. ``on_roster`` is False for one who has
    since left — the record of their visit stands, but there is no page
    left to send anybody to.
    """

    name: str
    rank: str
    miniature: object = None
    on_roster: bool = True


@dataclass(frozen=True)
class Receipt:
    """An open Visit Trading Post action, as the figures it is read by.

    Built for the screen rather than stored: what a visit added is the
    amount on the gang, what it has spent is the ledger's answer, and who
    went is the events the opening act wrote. Nothing here is a second
    copy of any of them.
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
        """What added the figure, as one line — "Leader, Champion × 2".

        What raised each fighter's contribution rather than who went,
        because this sits against the figure they add up to and answers
        where it came from. Who went is drawn beside it, by name, since
        that is the different question.

        In the order the visit wrote them, which is the order they were
        offered in: the bigger figure leads.

        A bare figure stands in the record where several things raised
        one fighter's contribution, and a figure is not a name to file
        anybody under, so it is left out of the line.
        """
        counts = {}
        for one in self.contributors:
            if not one.rank or one.rank.isdigit():
                continue
            counts[one.rank] = counts.get(one.rank, 0) + 1
        return ", ".join(
            rank if count == 1 else f"{rank} × {count}"
            for rank, count in counts.items()
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

    One query beyond what the figures already cost: who went, read off
    the batch the opening act stamped on every event it wrote.
    """
    from n26.core.models import LedgerEvent

    if not gang.visiting_trading_post:
        return None
    opened = (
        LedgerEvent.objects.filter(gang=gang, kind=LedgerEvent.Kind.TRADE_POINTS_SET)
        .order_by("-created")
        .first()
    )
    went = []
    if opened is not None and opened.batch is not None:
        went = [
            Contributor(
                name=event.miniature.name if event.miniature else "",
                rank=event.note,
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
        available=gang.starting_trade_points,
        spent=spent,
        remaining=gang.starting_trade_points - spent,
        contributors=tuple(went),
    )
