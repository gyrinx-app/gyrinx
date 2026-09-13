"""Resolve recorded fighter advancements from authored roll tables."""

from django.db import transaction

from n26.core.models import AdvancementSelection, Assignment
from n26.core.operations import Refusal


def _terms(terms):
    try:
        return (
            int(terms["roll"]),
            str(terms["pickable_id"]),
            str(terms["slot_assignment_id"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise Refusal(
            "Choose an advancement result and record its 2D6 roll."
        ) from error


def preview_advancement(record, configured, terms):
    """Return the exact authored and fighter state reviewed before completion."""
    roll, pickable_id, slot_assignment_id = _terms(terms)
    slot = configured.slot
    members = list(slot.picklist.members.select_related("pickable"))
    landed = slot.picklist.landing(roll, members)
    if not landed:
        landed = members
    offered = {str(member.pickable_id): member for member in landed}
    if pickable_id not in offered:
        raise Refusal("That advancement result is not available for this roll.")
    anchor = Assignment.objects.filter(
        pk=slot_assignment_id, miniature_root=record.fighter, archived=False
    ).first()
    if anchor is None or anchor.slot_id != slot.pk:
        raise Refusal("That advancement choice is no longer on this fighter.")
    pickable = offered[pickable_id].pickable
    return {
        "roll": roll,
        "slot_assignment_id": str(anchor.pk),
        "slot_id": str(slot.pk),
        "pickable_id": str(pickable.pk),
        "result": str(pickable),
        "rating": pickable.rating_contribution,
    }


@transaction.atomic
def apply_advancement(op, record, configured, terms):
    """Record the immutable roll and assign the reviewed advancement pick."""
    snapshot = preview_advancement(record, configured, terms)
    selection, created = AdvancementSelection.objects.get_or_create(
        action_record=record
    )
    if not created and selection.roll_event_id:
        if str(selection.intended_pick_id) != snapshot["pickable_id"]:
            raise Refusal("This advancement has already been rolled.")
        return snapshot
    anchor = Assignment.objects.get(pk=snapshot["slot_assignment_id"])
    pickable = configured.slot.picklist.members.get(
        pickable_id=snapshot["pickable_id"]
    ).pickable
    roll_event = op.roll(
        configured.slot, miniature=record.fighter, rolled=snapshot["roll"]
    )
    pick = op.choose(anchor, pickable, slot=configured.slot, roll=roll_event)
    selection.slot_assignment = anchor
    selection.roll_event = roll_event
    selection.intended_pick = pickable
    selection.pick_assignment = pick
    selection.save()
    return snapshot


def correct_advancement(op, record, configured, terms):
    """Refuse unsafe rewrites until dependent-change correction is available."""
    selection = record.advancement_selection
    snapshot = preview_advancement(record, configured, terms)
    if (
        str(selection.intended_pick_id) == snapshot["pickable_id"]
        and selection.roll_event.roll == snapshot["roll"]
    ):
        return snapshot
    raise Refusal(
        "This advancement cannot be changed while later changes depend on it."
    )
