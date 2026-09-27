"""Earned augmentation tiers available through the ordinary choice page."""

from n26.core.models import ActionRecord, Assignment, LedgerEvent, SlotSelection
from n26.library.models import PicklistMember


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
    # Older ordinary picks had no action record. Their opening ledger event
    # remains after a player switches to another earned tier or chooses none.
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


def highest_earned_level(found):
    """The highest tier earned for this exact item, including its live pick."""
    slot = found.slot
    anchor = slot.anchor.assignment
    levels = dict(
        PicklistMember.objects.filter(
            picklist_id=slot.slot.picklist_id, level__isnull=False
        ).values_list("pickable_id", "level")
    )
    picks = {
        pick.assignment.pickable_id
        for pick in slot.picks
        if pick.assignment is not None
    }
    picks.update(
        SlotSelection.objects.filter(
            slot_assignment=anchor,
            action_record__state=ActionRecord.State.COMPLETED,
        ).values_list("intended_pick_id", flat=True)
    )
    picks.update(
        Assignment.objects.filter(
            chosen_for=anchor,
            chosen_for_slot=slot.slot,
            pickable__isnull=False,
            ledger_events__kind=LedgerEvent.Kind.GRANTED,
            ledger_events__action_record__isnull=True,
        ).values_list("pickable_id", flat=True)
    )
    return max((levels.get(pick, 0) for pick in picks), default=0)


def earned_offer(offer, found, highest):
    """Keep the already-earned rungs and the optional empty choice."""
    from n26.core.render import NONE_KEY

    levels = dict(
        PicklistMember.objects.filter(
            picklist_id=found.slot.slot.picklist_id, level__lte=highest
        ).values_list("pickable_id", "level")
    )
    for group in offer.groups:
        group.options = [
            option
            for option in group.options
            if option.key == NONE_KEY
            or (option.thing is not None and option.thing.pk in levels)
        ]
    offer.groups = [group for group in offer.groups if group.options]
    return offer
