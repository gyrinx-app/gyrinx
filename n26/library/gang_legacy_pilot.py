"""Retiring the Gang Legacy slot pilot — a one-shot deletion.

An early experiment built a "Gang Legacy" slot type by hand: one slot,
one picklist, two pickables carrying nothing — no modifiers, no linked
category — and a handful of hand-placed assignments answering it on one
test gang. The pickables being hollow, those answers grant nothing; the
machinery is a name-squatter, and the names matter: slot types and
pickables are unique per pack, so the real Gang Legacy conversion
cannot build until these rows are gone.

Deletion is exactly why this is its own operation rather than part of
the conversion: conversions delete nothing, and the admin refuses the
cascade (player rows are registered read-only there, deliberately).
The rows die here instead, once, with an audit record, and with the
checks below standing between this and ever deleting anything that has
grown a purpose:

* every referencing assignment — archived included — must belong to
  **one** gang;
* every pickable must still be hollow;
* nothing outside the pilot may hang off the doomed assignments.

The plan/apply split is the conversion discipline's: ``find()`` reads
and describes, ``apply()`` performs exactly that, and the gang must
still reconcile afterwards — slots and picks are free, so retiring
them must not move its rating by a credit.
"""

from dataclasses import dataclass

from django.db import transaction


class Refused(Exception):
    """The retirement found the world grown past what it may delete."""


SLOT_TYPE = "Gang Legacy"


@dataclass(frozen=True)
class Pilot:
    """What stands, and what retiring it would delete."""

    slot_type_id: object = None
    slot_ids: tuple = ()
    picklist_ids: tuple = ()
    pickable_ids: tuple = ()
    assignment_ids: tuple = ()
    gang_id: object = None
    gang_said: str = ""
    events: int = 0
    problems: tuple = ()
    nothing_here: bool = False

    @property
    def ok(self):
        return not self.problems

    def preview(self):
        if self.nothing_here:
            return ["nothing to retire — no slot type of the pilot's name stands"]
        lines = [
            f"delete {len(self.assignment_ids)} assignment"
            f"{'' if len(self.assignment_ids) == 1 else 's'} on {self.gang_said}, "
            f"and the {self.events} history event"
            f"{'' if self.events == 1 else 's'} that describe them",
            f"delete the pilot's slot, its picklist, its "
            f"{len(self.pickable_ids)} hollow pickables, and the "
            f"“{SLOT_TYPE}” slot type",
            "prove the gang still reconciles, or refuse",
        ]
        return lines


def find():
    """Read the pilot as it stands. Never writes."""
    from n26.core.models import Assignment, LedgerEvent
    from n26.library.models import Pickable, Picklist, Slot, SlotType
    from n26.library.models.pack import default_pack_id

    # Scoped to the default pack: names are only unique per pack, and a
    # custom pack's own slot type of this name is somebody's content,
    # never the pilot.
    slot_type = SlotType.objects.filter(
        name=SLOT_TYPE, pack_id=default_pack_id()
    ).first()
    if slot_type is None:
        return Pilot(nothing_here=True)

    problems = []
    slots = list(Slot.objects.filter(slot_type=slot_type))
    picklists = list(Picklist.objects.filter(slot_type=slot_type))
    pickables = list(Pickable.objects.filter(slot_type=slot_type))

    for pickable in pickables:
        if pickable.modifiers.exists() or pickable.category_id is not None:
            problems.append(
                f"pickable “{pickable.name}” carries modifiers or links a "
                "category — the pilot was hollow, so this has grown a "
                "purpose and is not it"
            )

    doomed = list(
        Assignment.objects.filter(slot__in=slots)
        | Assignment.objects.filter(chosen_for_slot__in=slots)
        | Assignment.objects.filter(pickable__in=pickables)
    )
    gangs = {row.gang_root_id for row in doomed}
    if len(gangs) > 1:
        problems.append(
            f"the pilot's rows sit on {len(gangs)} gangs — expected one test "
            "gang, so somebody else has answered it"
        )

    # Nothing outside the pilot may be hanging off what dies: a child
    # assignment would cascade with its cause, its question, or its
    # parent, and this must never delete anything it has not named.
    doomed_pks = {row.pk for row in doomed}
    for row in doomed:
        hanging = (
            Assignment.objects.filter(caused_by=row)
            | Assignment.objects.filter(chosen_for=row)
            | Assignment.objects.filter(parent=row)
        )
        for child in hanging:
            if child.pk not in doomed_pks:
                problems.append(
                    f"assignment {child.pk} hangs off what the pilot would "
                    "delete but is not part of the pilot"
                )

    # Library content naming the doomed machinery protects it from
    # deletion — and means something has been authored against the
    # pilot, which is a purpose. Refuse in words rather than let the
    # delete crash.
    from n26.library.models import (
        AddsAssignable,
        DefaultAssignment,
        HasPickable,
        RemovesAssignable,
    )

    for said, found in (
        ("a built-in", DefaultAssignment.objects.filter(slot__in=slots)),
        (
            "a starting pick",
            DefaultAssignment.objects.filter(default_pickable__in=pickables),
        ),
        ("a grant", AddsAssignable.objects.filter(slot__in=slots)),
        ("a take-away", RemovesAssignable.objects.filter(slot__in=slots)),
        ("a condition", HasPickable.objects.filter(pickables__in=pickables)),
        (
            "another slot",
            Slot.objects.filter(picklist__in=picklists).exclude(
                pk__in=[s.pk for s in slots]
            ),
        ),
    ):
        if found.exists():
            problems.append(
                f"{said} names the pilot's machinery — something has been "
                "authored against it, which is a purpose"
            )

    events = LedgerEvent.objects.filter(assignment__in=doomed_pks).count()
    gang_id = next(iter(gangs), None)
    gang_said = str(doomed[0].gang_root) if doomed else "no gang at all"
    return Pilot(
        slot_type_id=slot_type.pk,
        slot_ids=tuple(s.pk for s in slots),
        picklist_ids=tuple(p.pk for p in picklists),
        pickable_ids=tuple(p.pk for p in pickables),
        assignment_ids=tuple(sorted(doomed_pks, key=str)),
        gang_id=gang_id,
        gang_said=gang_said,
        events=events,
        problems=tuple(problems),
    )


def apply(pilot):
    """Delete exactly what the pilot names, and prove the gang whole."""
    from n26.core.models import Assignment, Gang
    from n26.core.reconcile import assert_reconciled
    from n26.library.models import Pickable, Picklist, Slot, SlotType

    if pilot.problems:
        raise Refused("not retired: " + "; ".join(pilot.problems))
    if pilot.nothing_here:
        return list(pilot.preview())

    from django.db.models import ProtectedError

    report = list(pilot.preview())
    try:
        with transaction.atomic():
            # The history events describing these assignments ride the
            # deletion: ``LedgerEvent.assignment`` cascades, which is what
            # lets the preview promise them by count.
            Assignment.objects.filter(pk__in=pilot.assignment_ids).delete()
            Slot.objects.filter(pk__in=pilot.slot_ids).delete()
            # Members ride their picklist down; the pickables must outlive
            # them, so the order here is the constraint order.
            Picklist.objects.filter(pk__in=pilot.picklist_ids).delete()
            Pickable.objects.filter(pk__in=pilot.pickable_ids).delete()
            SlotType.objects.filter(pk=pilot.slot_type_id).delete()
            if pilot.gang_id is not None:
                gang = Gang.objects.get(pk=pilot.gang_id)
                try:
                    assert_reconciled(gang)
                except Exception as failed:
                    raise Refused(
                        f"refused — {gang} no longer reconciles: {failed}"
                    ) from failed
    except ProtectedError as protected:
        # The backstop behind find()'s enumerated checks: whatever this
        # names is a referent nobody listed, and the answer is the same
        # refusal in words, never a crash.
        raise Refused(
            "refused — something still names what the pilot would delete: "
            f"{sorted(str(obj) for obj in protected.protected_objects)[:5]}"
        ) from protected
    report.append("retired; the field is clean")
    return report
