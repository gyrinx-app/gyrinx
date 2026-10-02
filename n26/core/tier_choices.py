"""Recorded augmentation choices that keep equipment with its bearer."""

from n26.core.models import ActionRecord, Assignment, LedgerEvent, SlotSelection
from n26.library.models import Slot


def augmentation_bound_items(assignments):
    """Items with earned tiers, including any parent that would move them."""
    assignments = {assignment.pk: assignment for assignment in assignments}
    slot_ids = [pk for pk, assignment in assignments.items() if assignment.slot_id]
    if not slot_ids:
        return frozenset()
    slots = dict(
        Assignment.objects.filter(
            pk__in=slot_ids,
            archived=False,
            slot__mode=Slot.Mode.TIER_LADDER,
            slot__assigned_to=Slot.WillBeAssignedTo.BEARER,
            caused_by__isnull=False,
        ).values_list("pk", "caused_by_id")
    )
    earned = earned_slot_ids(list(slots))
    bound = set()
    for slot_id, item_id in slots.items():
        if str(slot_id) not in earned:
            continue
        pending = [item_id]
        while pending:
            item_id = pending.pop()
            if item_id not in assignments or item_id in bound:
                continue
            bound.add(item_id)
            item = assignments[item_id]
            pending.extend((item.parent_id, item.caused_by_id))
    return frozenset(bound)


def earned_slot_ids(slot_assignment_ids):
    """Slots with earned tiers, in a fixed number of queries for a card."""
    if not slot_assignment_ids:
        return set()
    from_actions = {
        str(pk)
        for pk in SlotSelection.objects.filter(
            slot_assignment_id__in=slot_assignment_ids,
            action_record__state=ActionRecord.State.COMPLETED,
        ).values_list("slot_assignment_id", flat=True)
    }
    # Manual picks have no action record. Their opening ledger event remains
    # after a player switches tiers or chooses none.
    from_choices = {
        str(pk)
        for pk in Assignment.objects.filter(
            chosen_for_id__in=slot_assignment_ids,
            pickable__isnull=False,
            ledger_events__kind=LedgerEvent.Kind.GRANTED,
            ledger_events__action_record__isnull=True,
        ).values_list("chosen_for_id", flat=True)
    }
    return from_actions | from_choices
