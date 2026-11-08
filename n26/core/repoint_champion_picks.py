"""Repoint live selections to equivalent pickables in their current slot's picklist.

A slot's changed picklist does not alter existing selections. This repair
requires exactly one same-name, same-slot-type replacement on the current
list when the selected pickable is absent. This distinguishes Champion
Archetype choices from gang-wide choices that share their names.

Preserve the pick's source, slot and cause. Leave archived picks unchanged.
Selections must have zero-valued entries, and every affected gang must
reconcile before commit.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Exists, OuterRef


class Refused(Exception):
    """The current assignments do not satisfy this repair's eligibility criteria."""


@dataclass(frozen=True)
class Adrift:
    """Every live pick naming something its slot's picklist no longer
    offers, grouped by gang."""

    #: ``(gang id, ((pick id, pickable id), ...))``, one per gang.
    gangs: tuple = ()
    problems: tuple = ()
    nothing_here: bool = False
    #: Archived picks in the same position, counted and left alone.
    archived: int = 0

    @property
    def ok(self):
        return not self.problems

    @property
    def pick_ids(self):
        return tuple(pk for _, moves in self.gangs for pk, _ in moves)

    def preview(self):
        lines = []
        if self.nothing_here:
            lines.append(
                "nothing to move — every live pick names something its "
                "slot's picklist offers"
            )
        for gang_id, moves in self.gangs:
            lines.append(
                f"gang {gang_id}: move {len(moves)} "
                f"pick{'' if len(moves) == 1 else 's'} onto the pickable of "
                "the same name on its slot's picklist"
            )
        if self.gangs:
            total = len(self.pick_ids)
            lines.append(
                f"{total} pick{'' if total == 1 else 's'} across "
                f"{len(self.gangs)} gang{'' if len(self.gangs) == 1 else 's'}"
            )
        if self.archived:
            lines.append(
                f"{self.archived} archived pick{'' if self.archived == 1 else 's'} "
                "naming something off the list, left alone"
            )
        return lines


def _adrift(archived=False):
    """Live picks of a slot that puts the pick on the model, naming a
    pickable that slot's picklist does not hold."""
    from n26.core.models import Assignment
    from n26.library.models import PicklistMember, Slot

    offered = PicklistMember.objects.filter(
        picklist_id=OuterRef("chosen_for_slot__picklist_id"),
        pickable_id=OuterRef("pickable_id"),
    )
    return (
        Assignment.objects.filter(
            chosen_for_slot__assigned_to=Slot.WillBeAssignedTo.BEARER,
            pickable__isnull=False,
            archived=archived,
        )
        .annotate(on_the_list=Exists(offered))
        .filter(on_the_list=False)
    )


def _same_name_on_the_list(pick):
    """Find one same-name, same-slot-type pickable in the current picklist.

    Match the player-visible name; author qualifiers distinguish content but are
    not shown in the choice. Report missing or ambiguous matches.
    """
    from n26.library.models import Pickable

    matches = list(
        Pickable.objects.filter(
            listed_on__picklist_id=pick.chosen_for_slot.picklist_id,
            slot_type_id=pick.pickable.slot_type_id,
            name__iexact=pick.pickable.name,
        )
    )
    if not matches:
        return None, (
            f"pick {pick.pk} names {pick.pickable.name}, and nothing of that "
            "name is on its slot's picklist — not the pick this moves"
        )
    if len(matches) > 1:
        return None, (
            f"pick {pick.pk} names {pick.pickable.name}, and its slot's "
            f"picklist offers {len(matches)} of that name, so which was "
            "meant cannot be read — not the pick this moves"
        )
    return matches[0], None


def find(gang_id=None):
    """Build a per-gang repair plan, optionally restricted to gang_id."""
    adrift = _adrift()
    archived_adrift = _adrift(archived=True)
    if gang_id is not None:
        adrift = adrift.filter(gang_root_id=gang_id)
        archived_adrift = archived_adrift.filter(gang_root_id=gang_id)
    picks = list(
        adrift.select_related("pickable", "chosen_for_slot").order_by("created", "id")
    )
    archived = archived_adrift.count()
    if not picks:
        return Adrift(nothing_here=True, archived=archived)

    problems = []
    by_gang = {}
    for pick in picks:
        if pick.gang_root_id is None:
            problems.append(
                f"pick {pick.pk} is rooted in no gang, so whose books it "
                "belongs to cannot be read — not the pick this moves"
            )
            continue
        if pick.pickable.slot_type_id != pick.chosen_for_slot.slot_type_id:
            problems.append(
                f"pick {pick.pk} names a {pick.pickable.slot_type_id} pickable "
                f"while its slot asks for {pick.chosen_for_slot.slot_type_id} "
                "— not the pick this moves"
            )
            continue
        replacement, problem = _same_name_on_the_list(pick)
        if problem is not None:
            problems.append(problem)
            continue
        by_gang.setdefault(pick.gang_root_id, []).append((pick.pk, replacement.pk))
    gangs = tuple(
        (gang_id, tuple(moves))
        for gang_id, moves in sorted(by_gang.items(), key=lambda kv: kv[0])
    )
    return Adrift(gangs=gangs, problems=tuple(problems), archived=archived)


def apply(adrift):
    """Apply each gang's repair in its own transaction and verify reconciliation.

    Report failures without changing those gangs or preventing other repairs.
    """
    if adrift.problems:
        raise Refused("not moved: " + "; ".join(adrift.problems))
    if adrift.nothing_here:
        return list(adrift.preview())

    report = list(adrift.preview())
    for gang_id, moves in adrift.gangs:
        report.append(_repoint_one(gang_id, moves))
    return report


def apply_one(gang_id):
    """Rederive and apply one gang's repair atomically, returning its report."""
    current = find(gang_id)
    if current.problems:
        return (
            f"gang {gang_id}: skipped — its picks no longer pass the move's "
            "checks: " + "; ".join(current.problems)
        )
    moves = dict(current.gangs).get(gang_id)
    if moves is None:
        return f"gang {gang_id}: nothing left to move"
    return _repoint_one(gang_id, moves)


def _repoint_one(gang_id, moves):
    """Replace one gang's eligible pick references and verify reconciliation atomically."""
    from n26.core.models import Assignment, Gang
    from n26.core.reconcile import check_gang, repin_everything

    with transaction.atomic():
        # Lock the gang before rederiving the plan from current selections.
        gang = Gang.objects.select_for_update().get(pk=gang_id)
        standing = dict(find(gang_id).gangs)
        if standing.get(gang_id) != moves:
            return (
                f"gang {gang_id}: skipped — its picks changed since the plan "
                "was read; read it again"
            )
        wanted = dict(moves)
        repointed = 0
        for pick in Assignment.objects.select_for_update().filter(pk__in=wanted):
            pick.pickable_id = wanted[pick.pk]
            pick.save()
            repointed += 1
        repin_everything(gang)
        gang.refresh_from_db()
        problems = check_gang(gang)
        if problems:
            transaction.set_rollback(True)
            return (
                f"gang {gang_id}: skipped — does not reconcile with its picks "
                "moved: " + "; ".join(problems)
            )
    return (
        f"gang {gang_id}: moved {repointed} "
        f"pick{'' if repointed == 1 else 's'} onto its slot's own pickables"
    )
