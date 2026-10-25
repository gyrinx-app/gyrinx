"""The purchase and models removed through a model's Delete or Refund action.

A generated model has no independent purchase. Its departure starts at the
assignment that brought it in, including hidden parts of that assignment.
Separately bought kit on every departing model is included as well.
"""

from collections import defaultdict
from dataclasses import dataclass

from n26.core.models import Assignment, Miniature
from n26.core.operations import Refusal


@dataclass(frozen=True)
class Departure:
    anchor: Assignment
    models: tuple[Miniature, ...]
    roots: tuple[Assignment, ...]
    stashable: tuple[Assignment, ...]
    refund: tuple[int, int]
    stash_refund: tuple[int, int]


def departure_for(miniature):
    """Prepare the same departure for its confirmation and its operation.

    A model's membership and the gang's founding are boundaries: taking a
    pet away must never remove its owner or the gang. Load the graph once;
    walking causes, hosted kit and ledger entries then issues no queries.
    """
    gang = miniature.gang
    assignments = {
        held.pk: held
        for held in Assignment.objects.filter(
            gang_root=gang, archived=False
        ).select_related("ledger_entry")
    }
    members = {
        model.membership_id: model
        for model in Miniature.objects.filter(
            membership__gang=gang, membership__archived=False
        ).only("id", "name", "membership_id")
    }
    anchor = assignments.get(miniature.membership_id)
    if anchor is None:
        raise Refusal(f"{miniature.name} has already left the roster.")
    while anchor.caused_by_id is not None:
        cause = assignments.get(anchor.caused_by_id)
        if cause is None or cause.pk == gang.founding_id or cause.pk in members:
            if anchor.pk == miniature.membership_id:
                raise Refusal(
                    f"You cannot remove {miniature.name} on its own. "
                    "Remove the assignment that brought it into the gang."
                )
            break
        anchor = cause

    dependants = defaultdict(set)
    kit = defaultdict(set)
    for held in assignments.values():
        for parent_id in (held.parent_id, held.caused_by_id):
            if parent_id in assignments:
                dependants[parent_id].add(held.pk)
        if held.miniature_id and held.parent_id is None:
            kit[held.miniature_id].add(held.pk)

    def walk(start, *, with_kit=False, keeping=frozenset()):
        found = set()
        pending = [start]
        while pending:
            pk = pending.pop()
            if pk in found:
                continue
            found.add(pk)
            pending.extend(dependants[pk])
            if with_kit and (model := members.get(pk)) is not None:
                pending.extend(kit[model.pk] - keeping)
        return found

    def refund_of(pks):
        credits = points = 0
        for pk in pks:
            entry = getattr(assignments[pk], "ledger_entry", None)
            if entry is not None:
                credits += entry.paid
                points += entry.trade_points
        return credits, points

    covered = walk(anchor.pk, with_kit=True)
    roots = tuple(
        held
        for held in assignments.values()
        if held.pk in covered
        and held.parent_id not in covered
        and held.caused_by_id not in covered
    )
    stashable = tuple(
        held
        for held in roots
        if held.pk != anchor.pk and refund_of(walk(held.pk))[0] > 0
    )
    # Moving kit also moves grants hosted beside it. They no longer
    # belong to the departing model's kit after the purchase is stashed.
    relocated = {
        pk
        for held in stashable
        for pk in walk(held.pk)
        if (part := assignments[pk]).parent_id is None
        and part.gang_id is None
        and (part.miniature_id, part.stash_id)
        == (held.miniature_root_id, held.stash_root_id)
    }
    after_stash = walk(anchor.pk, with_kit=True, keeping=relocated)
    return Departure(
        anchor=anchor,
        models=tuple(model for pk, model in members.items() if pk in covered),
        roots=roots,
        stashable=stashable,
        refund=refund_of(covered),
        stash_refund=refund_of(after_stash),
    )
