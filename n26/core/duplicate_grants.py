"""Remove duplicate catch-up grants and retain the original free assignment.

Match a provenance-tagged copy with a catch-up event to an untagged DEFAULT
copy of the same content on the same host. Exclude purchased or rewarded
copies, independently tagged set members, and ordinary acquisition grants.

Delete the duplicate and its caused descendants, transferring its provenance
to the retained original. Archiving would incorrectly record a removed
possession and leave the duplicate in provenance checks. Later reconciliation
can grant the survivor's nested built-ins once.

Matched copies must have zero-valued entries and events. Verify each gang
reconciles before its transaction commits.
"""

from dataclasses import dataclass, field

from django.db.models import Q

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
    #: Tallies carried from a dropped duplicate onto the copy that stays.
    merged: int = 0
    #: Reasons for retaining groups with paid assignments or counter history
    #: that cannot be transferred safely.
    kept_a_tally: list = field(default_factory=list)

    def counts(self):
        return {
            "dropped": self.dropped,
            "retagged": self.retagged,
            "swept": self.swept,
            "merged": self.merged,
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


def _goes_with(assignment):
    """Collect the full cascade graph through caused_by and materialised_for links."""
    found = set()
    frontier = {assignment.pk}
    while frontier:
        below = set(
            Assignment.objects.filter(
                Q(caused_by_id__in=frontier) | Q(materialised_for_id__in=frontier)
            ).values_list("pk", flat=True)
        )
        frontier = below - found - {assignment.pk}
        found |= frontier
    return found


def _money_under(assignment, goes_with):
    """Whether the duplicate's cascade contains paid or rating-bearing assignments.

    Spawned models may have acquired equipment independently, which this repair
    must preserve.
    """
    from n26.core.models import LedgerEntry

    return (
        LedgerEntry.objects.filter(assignment_id__in={assignment.pk} | goes_with)
        .exclude(paid=0, rating_contribution=0)
        .exists()
    )


def _tally_under(assignment, goes_with=None):
    """Return the highest counter value in the cascade, or None without counters."""
    from n26.core.models import CounterValue

    under = {assignment.pk} | (
        _goes_with(assignment) if goes_with is None else goes_with
    )
    values = CounterValue.objects.filter(assignment_id__in=under).values_list(
        "value", flat=True
    )
    return max(values, default=None)


def _verdict(grant, owner, gang=None):
    """Return the action and explanation shared by preview and execution."""
    goes_with = _goes_with(grant)
    where = grant.miniature_root or gang or "the gang"
    if _named_more_than_once(grant):
        return (
            "stands",
            f"{grant.assignable} on {where} is named by more than one "
            f"built-in of the same set, so which copy answers which cannot "
            f"be told and the duplicate stands.",
        )
    if _money_under(grant, goes_with):
        return (
            "stands",
            f"{grant.assignable} on {where} brought something that was paid "
            f"for, so its duplicate stands.",
        )
    tally = _tally_under(grant, goes_with)
    if tally and not _can_carry(grant, owner, goes_with):
        return (
            "stands",
            f"{grant.assignable} on {where} counts {tally} where the copy "
            f"already held has no place for it, so its duplicate stands.",
        )
    brought = (
        f", and the {len(goes_with)} thing{'' if len(goes_with) == 1 else 's'} "
        f"it brought"
        if goes_with
        else ""
    )
    counted = f" It counts {tally}, which moves across." if tally else ""
    return (
        "drops",
        f"{grant.assignable}: the caught-up copy goes{brought}, and the copy "
        f"already held takes its provenance.{counted}",
    )


def _named_more_than_once(grant):
    """Whether repeated set members make duplicate attribution ambiguous.

    Leave these groups unchanged because both copies may represent legitimate grants.
    """
    from n26.library.models import DefaultAssignment

    member = grant.materialised_from
    if member is None or member.assignable is None:
        return False
    field = Assignment.field_for(member.assignable)
    return (
        DefaultAssignment.objects.filter(
            default_set_id=member.default_set_id,
            archived=False,
            **{field: member.assignable},
        ).count()
        > 1
    )


def _can_carry(grant, owner, goes_with):
    """Whether a tally on the duplicate has a twin to move to."""
    from n26.core.models import CounterValue

    if grant.counter_id is None or owner.counter_id != grant.counter_id:
        return False
    # Something beneath the duplicate counts as well, and that has
    # nowhere to go.
    return not CounterValue.objects.filter(
        assignment_id__in=goes_with, value__gt=0
    ).exists()


def _carry_the_tally(grant, owner, tally, goes_with):
    """Transfer the duplicate counter's value to its retained twin when safe.

    Keep the larger balance. Nested counters without a matching twin prevent
    the duplicate's deletion.
    """
    from n26.core.models import CounterValue
    from n26.core.operations import operation

    if not tally:
        return True
    if not _can_carry(grant, owner, goes_with):
        return False
    with operation(owner.gang_root) as op:
        standing = (
            CounterValue.objects.filter(assignment=owner)
            .values_list("value", flat=True)
            .first()
        )
        if standing is None or standing < tally:
            op.tally(owner, tally - (standing or 0))
    return True


def duplicates_in(gang, only_miniature_id=None):
    """Pair catch-up grants with matching untagged originals on the same host.

    only_miniature_id restricts the read to one model.
    """
    caught_up = set(
        LedgerEvent.objects.filter(
            kind=LedgerEvent.Kind.CAUGHT_UP, gang=gang
        ).values_list("assignment_id", flat=True)
    )
    if not caught_up:
        return []

    live = Assignment.objects.filter(gang_root=gang, archived=False, removes=False)
    if only_miniature_id is not None:
        live = live.filter(miniature_root_id=only_miniature_id)
    live = list(live.select_related("ledger_entry"))
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
        # Pair oldest copies deterministically, at most one duplicate per retained
        # original. Extra catch-up grants remain independent.
        for grant, owner in zip(
            sorted(granted, key=lambda copy: copy.pk),
            sorted(owners, key=lambda copy: copy.pk),
            strict=False,
        ):
            pairs.append((grant, owner))
    return pairs


def de_duplicate(gang_id, only_miniature_id=None):
    """Delete safe duplicate grants and transfer provenance to retained originals.

    only_miniature_id confines changes to one model.
    """
    from django.db import transaction

    from n26.core.models import Gang
    from n26.core.reconcile import assert_reconciled

    outcome = GangOutcome(gang_id=str(gang_id))
    with transaction.atomic():
        # Read the repair plan under the same lock as ordinary counter writes.
        # Keep it until the duplicate and its history have been removed.
        gang = Gang.objects.select_for_update().get(pk=gang_id)
        # Deleting a duplicate can cascade through other candidate pairs. Skip
        # pairs whose duplicate or survivor was already deleted, preventing dangling
        # provenance writes.
        gone = set()
        for grant, owner in duplicates_in(gang, only_miniature_id):
            if grant.pk in gone or owner.pk in gone:
                continue
            action, sentence = _verdict(grant, owner, gang)
            if action == "stands":
                outcome.kept_a_tally.append(sentence)
                continue
            goes_with = _goes_with(grant)
            tally = _tally_under(grant, goes_with)
            if tally:
                _carry_the_tally(grant, owner, tally, goes_with)
                outcome.merged += 1
            swept = len(goes_with)
            member_id = grant.materialised_from_id
            carrier_id = grant.materialised_for_id
            grant.delete()
            gone |= {grant.pk} | goes_with
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


def what_one_model_carries(miniature):
    """Describe the exact duplicate repairs a single-model run would perform."""
    if miniature.membership_id is None:
        return []
    gang = miniature.membership.gang_root
    return [
        _verdict(grant, owner, gang)[1]
        for grant, owner in duplicates_in(gang, miniature.pk)
    ]
