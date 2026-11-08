"""Read Trading Post visit contributions and expenditure from effective cards and ledger events.

An open Activity records the visit's allowance. Purchases reference it for
Trade Point spending; closing the activity ends that allowance. A later
visit starts a separate allowance.

Offer fighters with positive readings of the hidden Trading Post visit
contribution counter. Content modifiers determine those contributions, including
changes to effective rank. Without the counter, opening requires an entered
allowance. Purchase destinations remain independent of attendance.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Visitor:
    """A potential visitor and effective Trade Point contribution.

    rank records the single contributing source name, or the numeric amount
    when several sources contributed.
    """

    miniature: object
    rank: str
    trade_points: int
    visiting: bool = False

    @property
    def key(self):
        return str(self.miniature.pk)


def computed_members(gang):
    """Compute the roster once for the visit and personal TP readers."""
    from n26.core.card import build_gang_card, build_modifier_index, carriers
    from n26.core.effects import compute, compute_gang

    card = build_gang_card(gang, with_statlines=False)
    index = build_modifier_index(carriers(card, *card.members.values()))
    compute_gang(card, index)
    return {pk: compute(member, index) for pk, member in card.members.items()}


def _readings(gang, counter, computed=None):
    """Read effective model contributions from cards computed gang-first.

    Share the gang computation and keep query count fixed as the roster grows.
    """
    from n26.core.effects import counter_readings

    # Omit characteristic prefetches because this read renders no model cards.
    computed = computed_members(gang) if computed is None else computed
    readings = {}
    for miniature_id, fold in computed.items():
        value = next(
            (
                reading.value
                for reading in counter_readings(fold.card, fold)
                if reading.thing.pk == counter.pk
            ),
            0,
        )
        readings[miniature_id] = (value, _raised_by(fold, counter) or str(value))
    return readings


def _raised_by(computed, counter):
    """Return the one named contribution source, or empty for multiple or stored sources."""
    named = {
        contribution.source
        for contribution in computed.counter_contributions
        if contribution.counter.pk == counter.pk
    }
    return named.pop() if len(named) == 1 else ""


def visitors(gang, going=None, members=None, *, computed=None):
    """List positive contributors by descending amount, then name.

    going supplies selected model IDs; None selects everyone, while an empty
    set selects none. Reuse members when the caller already loaded the roster.
    Content scopes prevent lower and higher ranks from contributing twice.
    """
    from n26.core.render import roster
    from n26.library.standard_content import visit_contribution_counter

    counter = visit_contribution_counter()
    if counter is None:
        return []
    readings = _readings(gang, counter, computed)
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
    """Build checkbox options grouped by effective contribution, largest first.

    Keep each model's contribution in its label. Group by the amount rather
    than rank because modifiers from different sources can produce equal totals.
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
                        name=f"{visitor.miniature.name} · {visitor.trade_points} TP",
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
    """A recorded visitor with the contribution source captured at attendance.

    Retain that source when the fighter later changes rank. ``miniature`` links
    to equipment while the model remains on the roster; ``on_roster=False``
    keeps the receipt without offering a stale destination.
    """

    name: str
    rank: str
    miniature: object = None
    on_roster: bool = True


@dataclass(frozen=True)
class Receipt:
    """An open visit's stored allowance, ledger expenditure and recorded visitors."""

    available: int
    spent: int
    remaining: int
    contributors: tuple[Contributor, ...] = ()

    @property
    def facts(self):
        """The allowance, spending and remainder in the shared tally structure."""
        from n26.core.confirm import Fact

        return (
            Fact("Available", str(self.available), sub=self.summary),
            Fact("Spent", str(self.spent)),
            Fact("Remaining", str(self.remaining), ruled=True, strong=True),
        )

    @property
    def summary(self):
        """Summarise named contribution sources in attendance order.

        Omit numeric fallback sources, which cannot name a rank or other provider.
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
    """Read the current visit's balance and attendance, or None when closed.

    Attendance uses the opening event's batch and adds one query beyond balances.
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
