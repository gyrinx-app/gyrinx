"""Dropping the second refund a doubled click wrote.

A refund, a sale and a removal each archive a line and write one event
saying so; a refund or a sale also settles the line's ledger entry. Where
the same click reached the server twice before the operation read the
line again under the gang's lock, the second arrival acted on a copy
loaded before the first had finished and wrote the same event again: two
``refunded`` or two ``sold`` legs for one purchase, and — for a fighter —
the removal legs of what they brought written twice as well. The entry's
pins say zero, the events fold to minus what the thing was worth, and
the gang's credits stand higher than its budget less its spending.

The books' invariant is that folding an entry's events reproduces the
entry, and the surplus legs are the only thing between these gangs and
it. Dropping them — every leg of a kind after the first on its line, and
every removal leg that rode in the same act — leaves one true story per
line, so the entries' pins already fit and the gang's pinned numbers
need only be written again. Deleting from an append-only ledger is the
sanctioned exception a repair earns the way a conversion does: it moves
no money of its own, and proves every affected gang reconciles or
unwinds whole.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Q


class Refused(Exception):
    """The repair found something other than the fault it was written for."""


@dataclass(frozen=True)
class Doubled:
    """Every surplus leg, grouped by the gang whose books carry it."""

    #: ``(gang id, surplus event ids, credits the gang was over)``, one
    #: per gang. The credits figure is what the surplus legs handed back:
    #: the gang's pinned credits fall by exactly this when they go.
    gangs: tuple = ()
    problems: tuple = ()
    nothing_here: bool = False

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
            lines.append(
                f"gang {gang_id}: drop {len(ids)} surplus "
                f"event{'' if len(ids) == 1 else 's'}; "
                f"its credits fall by {credits}"
            )
        total = len(self.event_ids)
        over = sum(credits for _, _, credits in self.gangs)
        lines.append(
            f"{total} surplus event{'' if total == 1 else 's'} across "
            f"{len(self.gangs)} gang{'' if len(self.gangs) == 1 else 's'}, "
            f"{over} credits handed back that were never owed"
        )
        return lines


def _surplus_events():
    """Every leg after the first of its kind on a line, and every removal
    leg written in the same act as one of those.

    Found in the ledger's own terms rather than by folding every gang's
    books: a line with two ``refunded`` or two ``sold`` events is the
    fault by definition, and the act that wrote the second is named by
    its batch mark — so the removal legs it wrote for the lines beneath
    are the ones sharing that mark that repeat an earlier removal.
    """
    from n26.core.models import LedgerEvent

    money_kinds = (LedgerEvent.Kind.REFUNDED, LedgerEvent.Kind.SOLD)
    doubled = (
        LedgerEvent.objects.filter(kind__in=money_kinds, assignment__isnull=False)
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
        repeats = LedgerEvent.objects.filter(
            batch__in=batches, kind=LedgerEvent.Kind.REMOVED
        ).order_by("created", "id")
        for event in repeats:
            # "Earlier" in the same total order the surplus legs above
            # were ranked by: created, then id. Two legs written in the
            # same instant still have one first, so an exact tie names
            # one of them and never both.
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


def find():
    """What stands to be dropped, gang by gang."""
    surplus = _surplus_events()
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
    return Doubled(gangs=gangs, problems=tuple(problems))


def apply(doubled):
    """Drop exactly what the plan names, and prove each gang's books whole.

    One transaction: a gang whose books still disagree after its surplus
    legs are gone unwinds the whole run, with the disagreement in words.
    """
    from n26.core.models import Gang, LedgerEvent
    from n26.core.reconcile import check_gang, repin_everything

    if doubled.problems:
        raise Refused("not repaired: " + "; ".join(doubled.problems))
    if doubled.nothing_here:
        return list(doubled.preview())

    report = list(doubled.preview())
    gang_ids = [gang_id for gang_id, _, _ in doubled.gangs]
    with transaction.atomic():
        # The gangs first, so nothing lands on their books while their
        # legs are being dropped; then the plan again, because it was
        # read before this transaction opened.
        list(Gang.objects.select_for_update().filter(pk__in=gang_ids).order_by("pk"))
        now = find()
        if now.problems or set(now.gangs) != set(doubled.gangs):
            raise Refused(
                "not repaired: the books have changed since the plan was "
                "read — read it again"
            )
        deleted, _ = LedgerEvent.objects.filter(pk__in=doubled.event_ids).delete()
        if deleted != len(doubled.event_ids):
            raise Refused(
                f"not repaired: {len(doubled.event_ids)} legs named, {deleted} found"
            )
        for gang_id in gang_ids:
            gang = Gang.objects.get(pk=gang_id)
            repin_everything(gang)
            gang.refresh_from_db()
            problems = check_gang(gang)
            if problems:
                raise Refused(
                    f"refused — gang {gang_id} still does not reconcile "
                    "with its surplus legs gone: " + "; ".join(problems)
                )

    report.append("dropped events " + ", ".join(str(pk) for pk in doubled.event_ids))
    report.append("repaired; every affected gang reconciles")
    return report
