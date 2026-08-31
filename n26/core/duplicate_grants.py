"""Dropping the second copy a catch-up pass granted.

A pass decides whether a carrier already holds a member by provenance
alone: a copy naming the member and the carrier. Grants written before
provenance existed name nothing, so to a pass they were invisible — it
looked at a model that plainly held the thing, found no copy naming the
member, and granted another. Every such pass over a set left the model
holding the thing twice: the owner's original, and a fresh grant told in
the history as caught up.

A duplicate is recognised by its shape rather than by when it happened:
one copy carrying provenance and a catch-up event, beside a copy of the
same thing on the same host with no provenance at all. Nothing else has
that shape. Two members of a set naming one thing leave two copies that
both carry provenance; a thing an owner bought or was rewarded leaves a
copy whose reason is not ``default``; a hire's own grant carries no
catch-up event.

The repair keeps the owner's copy and drops the pass's, then writes the
dropped copy's provenance onto the survivor — the state the estate would
have been in had every grant been tagged before any pass ran. Deleting
is right where archiving is not: an archived copy reads as something the
owner parted with, and they never had this one. What the dropped copy
caused goes with it, which is how a duplicated subtype's own built-ins
leave too; the next pass grants them once, against the survivor.

Nothing here moves money. Every copy dropped is a free grant whose entry
pins zero and whose events carry no deltas, so the books fold exactly as
they did — proved per gang, as every repair here proves it.
"""

from dataclasses import dataclass, field

from n26.core.models import Assignment, LedgerEvent, Reason
from n26.core.models.assignment import ASSIGNABLE_FIELDS

#: Grants written before provenance was recorded, in the shape that says
#: so. A removal is machinery rather than a grant and never counts.
UNTAGGED = {
    "materialised_from__isnull": True,
    "ledger_entry__reason": Reason.DEFAULT,
    "removes": False,
    "archived": False,
}


@dataclass
class GangOutcome:
    """What the repair did to one gang."""

    gang_id: str
    #: Duplicate grants deleted.
    dropped: int = 0
    #: Owner's copies given the dropped copy's provenance.
    retagged: int = 0
    #: Assignments that went with a dropped copy because it caused them.
    swept: int = 0
    #: Sentences, one per group left alone because dropping it would
    #: destroy a tally somebody had kept.
    kept_a_tally: list = field(default_factory=list)

    def counts(self):
        return {
            "dropped": self.dropped,
            "retagged": self.retagged,
            "swept": self.swept,
            "kept_a_tally": len(self.kept_a_tally),
        }


def _host_of(assignment):
    """What the copy hangs on: its model, or the gang where it has none."""
    if assignment.miniature_root_id is not None:
        return ("miniature", assignment.miniature_root_id)
    if assignment.stash_root_id is not None:
        return ("stash", assignment.stash_root_id)
    return ("gang", assignment.gang_root_id)


def _kind_of(assignment):
    for field_name in ASSIGNABLE_FIELDS:
        if getattr(assignment, f"{field_name}_id", None) is not None:
            return (field_name, getattr(assignment, f"{field_name}_id"))
    return None


def _tally_under(assignment):
    """The highest counter value on the copy or anything it caused, or
    None where nothing under it counts anything."""
    values = [
        row.counter_value.value
        for row in [assignment, *assignment.caused.all()]
        if getattr(row, "counter_value", None) is not None
    ]
    return max(values) if values else None


def duplicates_in(gang):
    """The pairs this gang carries: a caught-up grant beside an owner's
    untagged copy of the same thing on the same host."""
    caught_up = set(
        LedgerEvent.objects.filter(
            kind=LedgerEvent.Kind.CAUGHT_UP, gang=gang
        ).values_list("assignment_id", flat=True)
    )
    if not caught_up:
        return []

    live = list(
        Assignment.objects.filter(
            gang_root=gang, archived=False, removes=False
        ).select_related("ledger_entry")
    )
    by_place = {}
    for copy in live:
        kind = _kind_of(copy)
        if kind is None:
            continue
        by_place.setdefault((_host_of(copy), kind), []).append(copy)

    pairs = []
    for copies in by_place.values():
        if len(copies) < 2:
            continue
        granted = [
            copy
            for copy in copies
            if copy.pk in caught_up and copy.materialised_from_id is not None
        ]
        owners = [
            copy
            for copy in copies
            if copy.materialised_from_id is None
            and getattr(copy, "ledger_entry", None) is not None
            and copy.ledger_entry.reason == Reason.DEFAULT
        ]
        # Pairs only, deliberately: a group with more caught-up grants
        # than owner's copies has as many duplicates as there are copies
        # to keep, and the rest are grants standing on their own.
        for grant, owner in zip(
            sorted(granted, key=lambda copy: copy.pk), owners, strict=False
        ):
            pairs.append((grant, owner))
    return pairs


def de_duplicate(gang_id):
    """Settle one gang: drop each duplicated grant and hand its
    provenance to the copy the owner already had."""
    from django.db import transaction

    from n26.core.models import Gang
    from n26.core.reconcile import assert_reconciled

    gang = Gang.objects.get(pk=gang_id)
    outcome = GangOutcome(gang_id=str(gang_id))
    with transaction.atomic():
        for grant, owner in duplicates_in(gang):
            tally = _tally_under(grant)
            if tally:
                outcome.kept_a_tally.append(
                    f"{grant.assignable} on {grant.miniature_root or gang} "
                    f"counts {tally}, so its duplicate stands."
                )
                continue
            swept = grant.caused.count()
            member_id = grant.materialised_from_id
            carrier_id = grant.materialised_for_id
            grant.delete()
            owner.materialised_from_id = member_id
            owner.materialised_for_id = carrier_id
            owner.save(
                update_fields=["materialised_from", "materialised_for", "modified"]
            )
            outcome.dropped += 1
            outcome.retagged += 1
            outcome.swept += swept
        if outcome.dropped:
            gang.refresh_from_db()
            assert_reconciled(gang)
    return outcome


def duplicate_grants_by_kind():
    """How many caught-up grants sit beside an owner's untagged copy of
    the same thing, by what they name — the console's preview."""
    from collections import Counter

    counted = Counter()
    caught_up = set(
        LedgerEvent.objects.filter(kind=LedgerEvent.Kind.CAUGHT_UP).values_list(
            "assignment_id", flat=True
        )
    )
    untagged = {}
    for copy in Assignment.objects.filter(**UNTAGGED).select_related("ledger_entry"):
        kind = _kind_of(copy)
        if kind is not None:
            untagged.setdefault((_host_of(copy), kind), []).append(copy.pk)
    for copy in Assignment.objects.filter(
        pk__in=caught_up, archived=False, removes=False
    ):
        kind = _kind_of(copy)
        if kind is None:
            continue
        waiting = untagged.get((_host_of(copy), kind))
        if waiting:
            waiting.pop()
            counted[kind[0]] += 1
    return dict(counted)
