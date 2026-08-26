"""Checking the pinned numbers against what the ledger actually says.

Three things are written at write time rather than derived on read: an
assignment's roots, a ledger entry's totals, and a gang's rating. Each is a
cache, and each can be recomputed. These functions do the recomputing, so a
test (or a management command) can prove the caches are honest.
"""

from datetime import UTC, datetime

from django.db.models import DateTimeField, Subquery, Sum, Value
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


def trade_points_spent(gang):
    """Every Trade Point laid out since the allowance was last set.

    The allowance-set event is the boundary a trip is measured from, so
    what was spent on an earlier trip stops counting the moment a new
    allowance is written — which is what makes "set it again" the way to
    both begin a trip and end one.

    Summed from the events rather than from the entries because a refund
    settles its entry to zero and appends the returning event: reading
    the log keeps the two acts in the order they happened.

    The trip an event belongs to is the trip its *purchase* belongs to,
    not the trip its own event happened in. A refund is an event of its
    own, written whenever the owner gets round to it, so windowing on
    event time lets the undoing of an earlier trip's purchase land inside
    this one — handing back kit bought last time would mint Trade Points
    the visit never brought. Windowing on the assignment keeps a purchase
    and everything that later happens to it on the same side of the
    boundary, so the two either both count or neither does.

    Events about no assignment are outside this by construction: the
    boundary event itself is one, and none of them moves Trade Points.

    One query, boundary and all. Every screen showing what a gang has
    left asks this, and a gang's page is a fixed number of queries by
    invariant rather than by hope.
    """
    from n26.core.models import LedgerEvent

    since = (
        LedgerEvent.objects.filter(gang=gang, kind=LedgerEvent.Kind.TRADE_POINTS_SET)
        .order_by("-created")
        .values("created")[:1]
    )
    return (
        LedgerEvent.objects.filter(gang=gang)
        .filter(
            assignment__created__gte=Coalesce(
                Subquery(since),
                Value(_SINCE_ALWAYS, output_field=DateTimeField()),
            )
        )
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
