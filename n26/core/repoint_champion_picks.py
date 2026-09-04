"""Moving a pick onto the pickable its slot's picklist now offers.

A pick names the pickable that was picked and the slot that asked. The
slot draws from a picklist, and pointing the slot at a different list
moves nothing already picked: the pick goes on naming the pickable it
named, which the list the slot now reads may not hold at all.

That is what the Outcast archetypes leave behind. A Champion's Archetype
and the gang's were picked from one list, so one pickable carried both
readings; splitting them gives the Champion's slot a list of its own
holding a pickable of the same name for each archetype, and every
Champion's pick still names the gang's. Such a pick reads as chosen and
draws its name, and everything under it — the skill sets it places, the
powers it offers — is the gang's reading rather than the Champion's.

The repair finds every live pick whose slot puts the pick on the model
that made it, where the slot's picklist does not hold what was picked
and does hold exactly one pickable of the same slot type under the same
name — and points the pick at that one. Nothing else changes: the pick
still names the assignment that asked and the slot it settles, and it is
still caused by what caused it, so it still goes when that goes.

An archived pick is counted and left alone: it draws nothing, and
rewriting history is not a repair. No money moves — a pickable is priced
at nothing and every pick's entry pins zero — and each gang is proved to
reconcile before its own move commits.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Exists, OuterRef


class Refused(Exception):
    """The repair found something other than the fault it was written for."""


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
    """The one pickable on the slot's picklist that goes by the same
    name and belongs to the same slot type — or what is wrong instead.

    Matching is by the name a card prints, because that is the whole of
    what a player picked: two pickables of one name are told apart for
    authors by their qualifier, which never reaches anyone playing.
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
    """What stands to be moved, gang by gang. ``gang_id`` narrows the
    plan to that one gang."""
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
    """Move what the plan names, gang by gang, and prove each gang's
    books whole.

    Each gang is its own transaction: one that cannot be made whole is
    left exactly as it stood and reported, and the rest are repaired.
    """
    if adrift.problems:
        raise Refused("not moved: " + "; ".join(adrift.problems))
    if adrift.nothing_here:
        return list(adrift.preview())

    report = list(adrift.preview())
    for gang_id, moves in adrift.gangs:
        report.append(_repoint_one(gang_id, moves))
    return report


def _repoint_one(gang_id, moves):
    """One gang's move, committed or rolled back on its own. Returns the
    line the report carries for it."""
    from n26.core.models import Assignment, Gang
    from n26.core.reconcile import check_gang, repin_everything

    with transaction.atomic():
        # The gang first, so nothing lands on its books while its picks
        # are moving; then the plan again, because it was read before
        # this transaction opened.
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
