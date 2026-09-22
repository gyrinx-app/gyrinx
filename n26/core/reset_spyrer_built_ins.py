"""Remove the measured Spyre Hunters setup and its three action uses.

Identifiers, rather than names, bound this one-off repair. The staff test's
later manual tallies retain their deltas when its action payment is removed.
Other advancements, equipment and counter history remain unchanged.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q

GANG_TYPE_ID = "01KZGCS5713DSWMWPHN4PGP7ZC"
DEFAULT_SET_ID = "01KZWAJ72W1NKEKZ2AZH2EYPR8"
MEMBERS = {
    "01M34W99K0QDKMFX4ZEFAJT6GB": ("rule", "01M34W1VVPNV5VH2613T99VFVJ"),
    "01M34W9R0JH4Q4G8PNW9S3MV7T": ("rule", "01M34W1QPPP0BQFW4V7F6A7HZG"),
    "01M352RH75MNB44DPTFHSN2DX1": ("action", "01M32WNCG9MKYJVTQ4V0TC51S9"),
    "01M352S9P445YDVKA3MYC0675W": ("action", "01M32WNCJTCEVG8PXK5W19VFQX"),
}
USES = {
    "01M352Z5ZD6EGXNG5C8XDBXP1P": "cancelled",
    "01M3530FXWMT6YJ9GW7GF83MRQ": "completed",
    "01M357T2XR7RYN5F9EPBBYJCB5": "started",
}
# These manual staff-test adjustments followed the completed use. Their
# before/after balances move with the refund; their deltas are unchanged.
LATER_TALLIES = {
    "01M355GENG9WQ1P3C4GP95YVPB",
    "01M355GG5Q9GG5NZ8JHTVC1QWP",
    "01M355N8SPHCSFR0AA2S478CXH",
    "01M355NAAJTE5ZYQWC7DAAB752",
    "01M355NCFP5KDF0AK7CHDAF18X",
    "01M355NDS5HDQF0T1TR2JWANK7",
    "01M355NF6AYM91MB0AGM1514D7",
    "01M355NGG7N52HNR0MMCJ698MA",
    "01M355VP1TCGXRBM8NDR7FF2G6",
    "01M355VQE1J3RBFHDXWBXZ02RY",
    "01M3560VDCPWCQNFDZDG0GK0NS",
    "01M3560WS4JJJ1G27BW4D4N05K",
    "01M3560Y3EWTS11556BHN3ECCA",
    "01M3560ZEGDV60RJKYRZDBERJP",
}


class Refused(Exception):
    pass


@dataclass(frozen=True)
class Plan:
    gangs: tuple = ()
    members: tuple = ()
    uses: int = 0
    problems: tuple = ()

    @property
    def ok(self):
        return not self.problems

    @property
    def nothing_here(self):
        return not self.gangs and not self.members and not self.problems

    def preview(self):
        yield f"Remove {len(self.members)} mistaken Spyre Hunters built-ins."
        yield (
            f"Delete {sum(len(ids) for _, ids in self.gangs)} propagated assignments "
            f"across {len(self.gangs)} gangs and {self.uses} recorded action uses."
        )
        yield "Refund the staff test's Kill Count and Glitch Count payment, keeping its later manual adjustments."
        yield "Keep gangs, equipment, XP and other completed advancements."
        for gang_id, ids in self.gangs:
            yield f"Gang {gang_id}: delete {len(ids)} assignments."
        yield from self.problems


def _members():
    from n26.library.models import DefaultAssignment, GangType

    members = list(DefaultAssignment.objects.filter(pk__in=MEMBERS))
    if (
        members
        and not GangType.objects.filter(
            pk=GANG_TYPE_ID, built_ins_id=DEFAULT_SET_ID
        ).exists()
    ):
        raise Refused("The Spyre Hunters built-in set changed.")
    for member in members:
        kind, pk = MEMBERS[str(member.pk)]
        if (
            str(member.default_set_id) != DEFAULT_SET_ID
            or str(getattr(member, f"{kind}_id")) != pk
        ):
            raise Refused(f"Built-in {member.pk} no longer matches the measured setup.")
    return members


def _assignments(gang_id=None):
    from n26.core.models import Assignment

    assignments = Assignment.objects.filter(materialised_from_id__in=MEMBERS)
    if gang_id is not None:
        assignments = assignments.filter(gang_root_id=gang_id)
    return assignments.select_related(
        "gang_root", "materialised_for", "ledger_entry"
    ).order_by("gang_root_id", "pk")


def _validate(assignments):
    from n26.core.models import ActionRecord, Assignment, LedgerEvent

    ids = [assignment.pk for assignment in assignments]
    for assignment in assignments:
        kind, pk = MEMBERS[str(assignment.materialised_from_id)]
        entry = getattr(assignment, "ledger_entry", None)
        if (
            assignment.gang_id != assignment.gang_root_id
            or str(assignment.gang_root.gang_type_id) != GANG_TYPE_ID
            or assignment.materialised_for_id != assignment.gang_root.founding_id
            or assignment.caused_by_id != assignment.materialised_for_id
            or str(getattr(assignment, f"{kind}_id")) != pk
            or entry is None
            or any(
                (
                    entry.list_price,
                    entry.discount,
                    entry.paid,
                    entry.trade_points,
                    entry.rating_contribution,
                )
            )
        ):
            raise Refused(
                f"Assignment {assignment.pk} changed or has a non-zero value."
            )
    if Assignment.objects.filter(
        Q(caused_by_id__in=ids)
        | Q(parent_id__in=ids)
        | Q(materialised_for_id__in=ids)
        | Q(chosen_for_id__in=ids)
    ).exists():
        raise Refused("A mistaken assignment has dependent equipment or choices.")
    if (
        LedgerEvent.objects.filter(assignment_id__in=ids)
        .exclude(
            credits_delta=0,
            trade_points_delta=0,
            rating_delta=0,
            counter_before=None,
            before_pick=None,
            after_pick=None,
        )
        .exists()
    ):
        raise Refused("A mistaken assignment has additional ledger effects.")
    records = list(ActionRecord.objects.filter(source_assignment_id__in=ids))
    for record in records:
        if USES.get(str(record.pk)) != record.state:
            raise Refused(
                f"Action use {record.pk} changed since the reset was inspected."
            )
        if record.allowance_id is not None:
            raise Refused(f"Action use {record.pk} consumes an earned allowance.")
    return records


def _counter_restorations(records):
    from n26.core.models import CounterValue, LedgerEvent

    events = list(
        LedgerEvent.objects.filter(action_record__in=records).order_by("created", "pk")
    )
    allowed = {"use_started", "use_cancelled", "use_paid", "use_completed", "tallied"}
    counters = {}
    for event in events:
        if (
            event.kind not in allowed
            or any((event.credits_delta, event.trade_points_delta, event.rating_delta))
            or event.before_pick_id
            or event.after_pick_id
            or event.reversal_of_id
        ):
            raise Refused(f"Action event {event.pk} has effects outside this reset.")
        if event.counter_before is not None:
            counters.setdefault(event.assignment_id, []).append(event)
        elif event.assignment_id is not None:
            raise Refused(f"Action event {event.pk} changes an assignment.")
    if LedgerEvent.objects.filter(reversal_of__in=events).exists():
        raise Refused("An action use has been corrected.")
    restored = []
    shifted = []
    for assignment_id, removed in counters.items():
        tail = list(
            LedgerEvent.objects.filter(
                assignment_id=assignment_id,
                counter_before__isnull=False,
                created__gte=removed[0].created,
            ).order_by("created", "pk")
        )
        value = CounterValue.objects.get(assignment_id=assignment_id)
        removed_ids = {event.pk for event in removed}
        later = [event for event in tail if event.pk not in removed_ids]
        if (
            [event.pk for event in tail[: len(removed)]]
            != [event.pk for event in removed]
            or value.value != tail[-1].counter_after
            or any(
                str(event.pk) not in LATER_TALLIES
                or event.kind != "tallied"
                or event.action_record_id is not None
                or event.reversal_of_id is not None
                for event in later
            )
            or LedgerEvent.objects.filter(reversal_of__in=later).exists()
        ):
            raise Refused(f"Counter {assignment_id} changed after the action use.")
        refund = removed[0].counter_before - removed[-1].counter_after
        restored.append((value, value.value + refund))
        shifted.extend((event, refund) for event in later)
    return events, restored, shifted


def find():
    try:
        members = _members()
        assignments = list(_assignments())
        records = _validate(assignments)
        _counter_restorations(records)
    except Refused as exc:
        return Plan(problems=(str(exc),))
    by_gang = {}
    for assignment in assignments:
        by_gang.setdefault(assignment.gang_root_id, []).append(assignment.pk)
    return Plan(
        gangs=tuple((pk, tuple(ids)) for pk, ids in by_gang.items()),
        members=tuple(member.pk for member in members),
        uses=len(records),
    )


@transaction.atomic
def prepare():
    """Stop further propagation before taking the gang work-list."""
    from n26.library.authoring import remove_default_member

    plan = find()
    if not plan.ok:
        raise Refused("; ".join(plan.problems))
    for member in _members():
        if not member.archived:
            remove_default_member(member)
    if not plan.gangs:
        finish()
        return Plan()
    return plan


def apply_one(gang_id):
    from n26.core.models import ActionRecord, Assignment, Gang, LedgerEvent
    from n26.core.operations import operation
    from n26.core.reconcile import assert_reconciled

    gang = Gang.objects.get(pk=gang_id)
    with operation(gang):
        assert_reconciled(gang)
        assignments = list(_assignments(gang_id).select_for_update(of=("self",)))
        records = _validate(assignments)
        events, restored, shifted = _counter_restorations(records)
        ids = [assignment.pk for assignment in assignments]
        # Selections would own results outside the three measured uses.
        for record in records:
            if any(
                hasattr(record, name)
                for name in (
                    "slot_selection",
                    "advancement_selection",
                    "skill_selection",
                )
            ):
                raise Refused(f"Action use {record.pk} has a selected result.")
        LedgerEvent.objects.filter(pk__in=[event.pk for event in events]).delete()
        ActionRecord.objects.filter(pk__in=[record.pk for record in records]).delete()
        for event, refund in shifted:
            event.counter_before += refund
            event.counter_after += refund
            event.save(update_fields=["counter_before", "counter_after", "modified"])
        for value, before in restored:
            value.value = before
            value.save(update_fields=["value", "modified"])
        Assignment.objects.filter(pk__in=ids).delete()
        finish()
        assert_reconciled(gang)
    return f"Gang {gang_id}: deleted {len(ids)} assignments and {len(records)} action uses."


@transaction.atomic
def finish():
    """Delete the retired memberships only after their copies are gone."""
    from n26.core.models import Assignment

    if Assignment.objects.filter(materialised_from_id__in=MEMBERS).exists():
        return
    for member in _members():
        member.delete()
