"""Checking the pinned numbers against what the ledger actually says.

Three things are written at write time rather than derived on read: an
assignment's roots, a ledger entry's totals, and a gang's rating. Each is a
cache, and each can be recomputed. These functions do the recomputing, so a
test (or a management command) can prove the caches are honest.
"""

from datetime import UTC, datetime

from django.db.models import DateTimeField, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from n26.core.models import Assignment, LedgerEntry
from n26.core.models.assignment import ASSIGNABLE_FIELDS

#: Everything needed to resolve an entry's assignable without extra queries.
_ENTRY_RELATED = ("assignment", *(f"assignment__{f}" for f in ASSIGNABLE_FIELDS))


class Discrepancy(Exception):
    """Raised when a pinned value disagrees with a recomputed one."""


def check_entry(entry):
    """Folding an entry's events must reproduce the entry. Returns problems."""
    events = entry.assignment.ledger_events.all()
    problems = []
    for field, delta in [
        ("paid", "credits_delta"),
        ("trade_points", "trade_points_delta"),
        ("rating_contribution", "rating_delta"),
    ]:
        folded = sum(getattr(event, delta) for event in events)
        pinned = getattr(entry, field)
        if folded != pinned:
            problems.append(
                f"{entry.assignable}: {field} pinned {pinned}, events fold to {folded}"
            )
    if entry.paid != entry.list_price - entry.discount:
        problems.append(
            f"{entry.assignable}: paid {entry.paid} != list {entry.list_price} "
            f"- discount {entry.discount}"
        )
    return problems


def sum_rating(**root):
    """Sum rating over live assignments under a root.

    Archived assignments are skipped: a sold weapon stops counting, while its
    ledger entry stays a true statement of what it was worth.

    ``sum_rating(gang_root=gang)`` or ``sum_rating(miniature_root=model)``.
    """
    lookups = {f"assignment__{key}": value for key, value in root.items()}
    return (
        LedgerEntry.objects.filter(assignment__archived=False, **lookups)
        # A model whose membership has gone is off the roster, and so is
        # everything it was carrying — the assignments keep their pinned
        # roots, so they have to be filtered out here.
        .exclude(assignment__miniature_root__membership__archived=True)
        .aggregate(total=Sum("rating_contribution"))["total"]
        or 0
    )


def recomputed_rating(gang):
    """A gang's rating, summed fresh from its ledger entries.

    The stash is excluded, as in ``Gang.recompute_rating``: rating is
    what the models are worth; stashed gear counts in wealth.
    """
    return sum_rating(gang_root=gang, stash_root__isnull=True)


def total_spent(gang):
    """Every credit the gang has laid out, summed from the event log.

    Includes events on archived assignments — removing something is not a
    refund. A refund and a sale each append an event of their own, so both
    show here as spend coming back.
    """
    from n26.core.models import LedgerEvent

    return (
        LedgerEvent.objects.filter(assignment__gang_root=gang).aggregate(
            total=Sum("credits_delta")
        )["total"]
        or 0
    )


#: What "since the allowance was set" means for a gang that has never
#: set one: since always. A gang can spend at a post without an allowance
#: — the purchase asks first and then goes through — so those points have
#: to count against nothing rather than not count at all.
_SINCE_ALWAYS = datetime(1, 1, 1, tzinfo=UTC)


def trade_points_spent_for(action):
    """Every Trade Point that counted against one action.

    A purchase records the action it counted against on its ledger entry,
    so this is a sum over what points at that row — no window, no
    ordering, and an exact figure for an action long since closed.

    Summed from the events rather than from the entries because a refund
    settles its entry to zero and appends the returning event: reading
    the log keeps the two acts in the order they happened. The refund's
    event sits on the assignment the purchase made, so it lands on the
    action the purchase counted against however long afterwards the
    owner gets round to handing the thing back.

    One query.
    """
    from n26.core.models import LedgerEvent

    return (
        LedgerEvent.objects.filter(assignment__ledger_entry__action=action).aggregate(
            total=Sum("trade_points_delta")
        )["total"]
        or 0
    )


def trade_points_spent_by(action, miniature):
    """Every Trade Point one model spent against one action.

    The same sum as :func:`trade_points_spent_for`, narrowed to whoever
    spent it: a founding allowance is the model's own, so what one has
    spent says nothing about what another may.

    Narrowed on the buyer the purchase recorded and never on where the
    thing is now. An owner may move a gun into the stash or hand it to
    somebody else, and neither hands the points back — moving kit about
    is not a refund. Reading the assignment's model instead would refill
    the buyer's allowance the moment they stashed anything, and refunding
    the gun from its new owner would take that owner's allowance below
    zero for points they never spent.

    One query.
    """
    from n26.core.models import LedgerEvent

    return (
        LedgerEvent.objects.filter(
            assignment__ledger_entry__action=action,
            assignment__ledger_entry__spent_by=miniature,
        ).aggregate(total=Sum("trade_points_delta"))["total"]
        or 0
    )


def trade_points_spent(gang):
    """What the gang's open Visit Trading Post action has spent.

    Two sets of purchases, summed in one query. The first is what points
    at the gang's open visit, which is the whole of it for a purchase
    that recorded one — asked as a join rather than by naming the row, so
    nothing has to know which visit is open before asking. The second is
    a purchase under this visit that names no action at all — one
    written before the visit had a row to point at — found instead by
    when its assignment was created, measured from the boundary event
    the visit wrote. The second half is here only while such purchases
    exist.

    Either way the visit an event belongs to is the visit its *purchase*
    belongs to, and never the visit its own event happened in. A refund
    is an event of its own, written whenever the owner gets round to it,
    so counting by event time would let the undoing of an earlier
    visit's purchase land inside this one — handing back kit bought last
    time would mint Trade Points the visit never brought.

    Events about no assignment are outside this by construction: the
    boundary event itself is one, and none of them moves Trade Points.

    One query, boundary and all. Every screen showing what a gang has
    left asks this, and a gang's page is a fixed number of queries by
    invariant rather than by hope.
    """
    from n26.core.models import Action, LedgerEvent

    since = (
        LedgerEvent.objects.filter(gang=gang, kind=LedgerEvent.Kind.TRADE_POINTS_SET)
        .order_by("-created")
        .values("created")[:1]
    )
    unstamped = Q(
        assignment__ledger_entry__action__isnull=True,
        assignment__created__gte=Coalesce(
            Subquery(since),
            Value(_SINCE_ALWAYS, output_field=DateTimeField()),
        ),
    )
    counted = unstamped | Q(
        assignment__ledger_entry__action__gang=gang,
        assignment__ledger_entry__action__kind=Action.Kind.TRADING_POST_VISIT,
        assignment__ledger_entry__action__closed__isnull=True,
    )
    return (
        LedgerEvent.objects.filter(gang=gang)
        .filter(counted)
        .aggregate(total=Sum("trade_points_delta"))["total"]
        or 0
    )


def check_roots(assignment):
    """The pinned roots must match what the host chain says."""
    expected_gang, expected_mini = assignment.gang_root_id, assignment.miniature_root_id
    assignment._set_roots()
    problems = []
    if assignment.gang_root_id != expected_gang:
        problems.append(f"{assignment}: gang root drifted")
    if assignment.miniature_root_id != expected_mini:
        problems.append(f"{assignment}: model root drifted")
    return problems


def check_gang(gang):
    """Every check, for one gang. Returns a list of problems; empty is good."""
    problems = []
    for assignment in Assignment.objects.filter(gang_root=gang).select_related(
        "parent", "miniature"
    ):
        problems += check_roots(assignment)
    for entry in LedgerEntry.objects.filter(assignment__gang_root=gang).select_related(
        *_ENTRY_RELATED
    ):
        problems += check_entry(entry)
    stash = getattr(gang, "stash", None)
    if stash is not None:
        stash_sum = sum_rating(stash_root=stash)
        if stash.rating != stash_sum:
            problems.append(
                f"{stash}: rating pinned {stash.rating}, ledger sums to {stash_sum}"
            )
    recomputed = recomputed_rating(gang)
    if gang.rating != recomputed:
        problems.append(
            f"{gang}: rating pinned {gang.rating}, ledger sums to {recomputed}"
        )

    expected_credits = gang.recompute_credits()
    if expected_credits is None:
        expected_credits = 0  # no budget: nothing to count down from
    if gang.credits != expected_credits:
        problems.append(
            f"{gang}: credits pinned {gang.credits}, budget less spend is "
            f"{expected_credits}"
        )

    for miniature in models_in(gang):
        recomputed = miniature.recompute_rating()
        if miniature.rating != recomputed:
            problems.append(
                f"{miniature}: rating pinned {miniature.rating}, "
                f"ledger sums to {recomputed}"
            )
    return problems


def models_in(gang):
    """Every model in the gang, via its membership assignment."""
    from n26.core.models import Miniature

    return Miniature.objects.filter(membership__gang=gang)


def assert_reconciled(gang):
    problems = check_gang(gang)
    if problems:
        raise Discrepancy("; ".join(problems))


def ledger_for_gang(gang):
    """Every ledger entry anywhere in the gang — one indexed query."""
    return LedgerEntry.objects.filter(assignment__gang_root=gang).select_related(
        *_ENTRY_RELATED
    )


def ledger_for_miniature(miniature):
    """Every ledger entry anywhere on the model — one indexed query."""
    return LedgerEntry.objects.filter(
        assignment__miniature_root=miniature
    ).select_related(*_ENTRY_RELATED)


def repin_everything(gang):
    """Rewrite every pinned number for a gang. The repair to reconcile's report."""
    for miniature in models_in(gang):
        miniature.repin_rating()
    stash = getattr(gang, "stash", None)
    if stash is not None:
        stash.repin_rating()
    gang.repin_rating()
    gang.repin_credits()
