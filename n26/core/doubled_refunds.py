"""Repair duplicate refund, sale and removal events while preserving one valid removal.

Duplicate submissions can record repeated events against one archived
assignment. The entry then disagrees with the folded events and gang totals.
Find repeated events by assignment and kind, plus repeated dependent removals
sharing a surplus event's batch.

Delete only the surplus records and repin totals. This repair is an explicit
exception to append-only history: each affected gang must reconcile before
its transaction commits. A failure rolls back that gang without blocking others.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Q


class Refused(Exception):
    """The planned records do not match this repair's duplicate-event criteria."""


@dataclass(frozen=True)
class Doubled:
    """Surplus event IDs and balance adjustments grouped by gang."""

    #: Per-gang surplus event IDs and excess credits to remove from cached totals.
    gangs: tuple = ()
    problems: tuple = ()
    nothing_here: bool = False
    #: Gangs whose corrected balance would be negative remain unchanged and
    #: are reported for a separate balance decision.
    overspent: tuple = ()

    @property
    def ok(self):
        return not self.problems

    @property
    def event_ids(self):
        return tuple(pk for _, ids, _ in self.gangs for pk in ids)

    def preview(self):
        if self.nothing_here:
            return ["nothing to drop — no line carries a second refund or sale"]
        lines = []
        for gang_id, ids, credits in self.gangs:
            line = (
                f"gang {gang_id}: drop {len(ids)} surplus "
                f"event{'' if len(ids) == 1 else 's'}; "
                f"its credits fall by {credits}"
            )
            if gang_id in self.overspent:
                line += (
                    " — WOULD BE SKIPPED: it spent what it was never owed, "
                    "and its credits cannot fall below zero; decide by hand"
                )
            lines.append(line)
        total = len(self.event_ids)
        over = sum(credits for _, _, credits in self.gangs)
        lines.append(
            f"{total} surplus event{'' if total == 1 else 's'} across "
            f"{len(self.gangs)} gang{'' if len(self.gangs) == 1 else 's'}, "
            f"{over} credits handed back that were never owed"
        )
        return lines


def _surplus_events(gang_id=None):
    """Find duplicate settlement events and associated repeated removals for one gang.

    Keep the first refund or sale of each kind per assignment. Its later
    same-kind events identify surplus batches; remove repeated descendant removal
    events from those batches as well.
    """
    from n26.core.models import LedgerEvent

    events = LedgerEvent.objects.all()
    if gang_id is not None:
        events = events.filter(gang_id=gang_id)
    money_kinds = (LedgerEvent.Kind.REFUNDED, LedgerEvent.Kind.SOLD)
    doubled = (
        events.filter(kind__in=money_kinds, assignment__isnull=False)
        .values("assignment_id", "kind")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
    )
    surplus = []
    for row in doubled:
        legs = list(
            LedgerEvent.objects.filter(
                assignment_id=row["assignment_id"], kind=row["kind"]
            ).order_by("created", "id")
        )
        surplus.extend(legs[1:])

    batches = {event.batch for event in surplus if event.batch is not None}
    if batches:
        repeats = events.filter(
            batch__in=batches, kind=LedgerEvent.Kind.REMOVED
        ).order_by("created", "id")
        for event in repeats:
            # Use the same created-then-ID order as surplus ranking so simultaneous
            # events still have one deterministic first event.
            earlier = (
                LedgerEvent.objects.filter(
                    assignment_id=event.assignment_id,
                    kind=LedgerEvent.Kind.REMOVED,
                )
                .filter(
                    Q(created__lt=event.created)
                    | Q(created=event.created, id__lt=event.id)
                )
                .exists()
            )
            if earlier:
                surplus.append(event)
    return surplus


def find(gang_id=None):
    """Plan duplicate-event removals, optionally restricted to one gang."""
    surplus = _surplus_events(gang_id)
    if not surplus:
        return Doubled(nothing_here=True)

    problems = []
    by_gang = {}
    for event in surplus:
        if not event.assignment.archived:
            problems.append(
                f"a surplus {event.get_kind_display().lower()} leg stands on a "
                f"line still on the roster (gang {event.gang_id}) — not the "
                "doubled removal this repairs"
            )
        ids, credits = by_gang.setdefault(event.gang_id, ([], 0))
        ids.append(event.pk)
        by_gang[event.gang_id] = (ids, credits - event.credits_delta)
    gangs = tuple(
        (gang_id, tuple(ids), credits)
        for gang_id, (ids, credits) in sorted(by_gang.items(), key=lambda kv: kv[0])
    )
    return Doubled(gangs=gangs, problems=tuple(problems), overspent=_overspent(by_gang))


def _overspent(by_gang):
    """Find finite-budget gangs whose corrected credits would become negative."""
    from n26.core.models import Gang

    short = []
    for gang_id, credits, budget in Gang.objects.filter(pk__in=by_gang).values_list(
        "pk", "credits", "starting_credits"
    ):
        if budget is not None and credits - by_gang[gang_id][1] < 0:
            short.append(gang_id)
    return tuple(sorted(short))


def apply(doubled):
    """Apply each gang's planned repair in its own transaction and verify reconciliation.

    Report failures and leave their gangs unchanged. Removing surplus credits
    can make a gang insolvent; resolving that balance requires a separate decision.
    """
    if doubled.problems:
        raise Refused("not repaired: " + "; ".join(doubled.problems))
    if doubled.nothing_here:
        return list(doubled.preview())

    report = list(doubled.preview())
    for gang_id, ids, _ in doubled.gangs:
        report.append(_repair_one(gang_id, ids))
    return report


def apply_one(gang_id):
    """Rederive and apply one gang's repair in its own transaction, returning its report."""
    current = find(gang_id)
    if current.problems:
        return (
            f"gang {gang_id}: skipped — its books no longer pass the repair's "
            "checks: " + "; ".join(current.problems)
        )
    standing = {g: legs for g, legs, _ in current.gangs}
    ids = standing.get(gang_id)
    if ids is None:
        return f"gang {gang_id}: nothing left to drop"
    return _repair_one(gang_id, ids)


def _repair_one(gang_id, ids):
    """Repair and verify one gang atomically, returning its report."""
    from n26.core.models import Gang, LedgerEvent
    from n26.core.reconcile import check_gang, repin_everything

    with transaction.atomic():
        # Lock the gang before rederiving the plan from current ledger state.
        gang = Gang.objects.select_for_update().get(pk=gang_id)
        standing = {g: legs for g, legs, _ in find(gang_id).gangs}
        if standing.get(gang_id) != ids:
            return (
                f"gang {gang_id}: skipped — its books changed since the plan "
                "was read; read it again"
            )
        deleted, _ = LedgerEvent.objects.filter(pk__in=ids).delete()
        if deleted != len(ids):
            transaction.set_rollback(True)
            return f"gang {gang_id}: skipped — {len(ids)} legs named, {deleted} found"
        expected = gang.recompute_credits()
        if expected is not None and expected < 0:
            transaction.set_rollback(True)
            return (
                f"gang {gang_id}: skipped — dropping its surplus legs would "
                f"leave it {-expected} credits overspent; it spent what it was "
                "never owed, and what to do about that is a decision, not a "
                "repair"
            )
        repin_everything(gang)
        gang.refresh_from_db()
        problems = check_gang(gang)
        if problems:
            transaction.set_rollback(True)
            return (
                f"gang {gang_id}: skipped — still does not reconcile with its "
                "surplus legs gone: " + "; ".join(problems)
            )
    return (
        f"gang {gang_id}: dropped {len(ids)} event{'' if len(ids) == 1 else 's'}; "
        f"credits now {gang.credits}"
    )
