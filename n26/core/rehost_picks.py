"""Move misplaced model-hosted picks to their slot's gang destination.

A slot's host setting does not move existing picks. Find live model-hosted
picks whose slot specifies the gang, distinguishing them from deliberate
per-model choices provided by a gang-owned source.

Move only the pick's host. Preserve its choice identity and cause, so the
original model's choice remains resolved and source removal still cascades.
Independently hosted descendants stay on their current hosts. Leave archived
picks unchanged and verify every affected gang reconciles before commit.
"""

from dataclasses import dataclass

from django.db import transaction


class Refused(Exception):
    """The current assignments do not satisfy this repair's eligibility criteria."""


@dataclass(frozen=True)
class Astray:
    """Every live pick sitting on a model while its slot points at the
    gang, grouped by gang."""

    #: ``(gang id, pick ids)``, one per gang.
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
        return tuple(pk for _, ids in self.gangs for pk in ids)

    def preview(self):
        lines = []
        if self.nothing_here:
            lines.append(
                "nothing to move — every live pick of a slot that points at "
                "the gang sits on the gang"
            )
        for gang_id, ids in self.gangs:
            lines.append(
                f"gang {gang_id}: move {len(ids)} pick{'' if len(ids) == 1 else 's'} "
                "off its models onto the gang"
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
                "on a model, left alone"
            )
        return lines


def _astray(archived=False):
    """The picks on a model whose slot points at the gang."""
    from n26.core.models import Assignment
    from n26.library.models import Slot

    return Assignment.objects.filter(
        chosen_for_slot__assigned_to=Slot.WillBeAssignedTo.GANG,
        archived=archived,
        miniature__isnull=False,
    )


def _asked_of_this_model(pick):
    """Whether the pick originates from this model rather than a gang-owned source.

    Gang-carried offers can deliberately select onto individual members. Such
    picks must remain model-hosted; moving them would broadcast one model's
    selection to the entire gang.
    """
    asked = pick.chosen_for
    return asked is not None and asked.miniature_root_id == pick.miniature_id


def find(gang_id=None):
    """Build a per-gang repair plan, optionally restricted to gang_id."""
    astray = _astray()
    archived_astray = _astray(archived=True)
    if gang_id is not None:
        astray = astray.filter(gang_root_id=gang_id)
        archived_astray = archived_astray.filter(gang_root_id=gang_id)
    picks = list(
        astray.select_related("miniature__membership", "chosen_for").order_by(
            "created", "id"
        )
    )
    archived = archived_astray.count()
    if not picks:
        return Astray(nothing_here=True, archived=archived)

    problems = []
    by_gang = {}
    for pick in picks:
        membership = getattr(pick.miniature, "membership", None)
        if membership is None or membership.gang_id != pick.gang_root_id:
            problems.append(
                f"pick {pick.pk} sits on a model that is not a member of the "
                f"gang it is rooted in ({pick.gang_root_id}) — not the stray "
                "pick this moves"
            )
            continue
        if pick.chosen_for_id is None:
            problems.append(
                f"pick {pick.pk} names no choice it settles, so whose choice "
                "it was cannot be read — not the stray pick this moves"
            )
            continue
        if not _asked_of_this_model(pick):
            problems.append(
                f"pick {pick.pk} settles a choice the gang carries for each "
                "of its models, and was made for this one on purpose — not "
                "the stray pick this moves"
            )
            continue
        by_gang.setdefault(pick.gang_root_id, []).append(pick.pk)
    gangs = tuple(
        (gang_id, tuple(ids))
        for gang_id, ids in sorted(by_gang.items(), key=lambda kv: kv[0])
    )
    return Astray(gangs=gangs, problems=tuple(problems), archived=archived)


def apply(astray):
    """Apply each gang's repair in its own transaction and verify reconciliation.

    Report failures without changing those gangs or preventing other repairs.
    """
    if astray.problems:
        raise Refused("not moved: " + "; ".join(astray.problems))
    if astray.nothing_here:
        return list(astray.preview())

    report = list(astray.preview())
    for gang_id, ids in astray.gangs:
        report.append(_rehost_one(gang_id, ids))
    return report


def apply_one(gang_id):
    """Rederive and apply one gang's repair atomically, returning its report."""
    current = find(gang_id)
    if current.problems:
        return (
            f"gang {gang_id}: skipped — its picks no longer pass the move's "
            "checks: " + "; ".join(current.problems)
        )
    ids = dict(current.gangs).get(gang_id)
    if ids is None:
        return f"gang {gang_id}: nothing left to move"
    return _rehost_one(gang_id, ids)


def _rehost_one(gang_id, ids):
    """Move one gang's eligible picks and verify reconciliation in its transaction."""
    from n26.core.models import Assignment, Gang
    from n26.core.reconcile import check_gang, repin_everything

    with transaction.atomic():
        # Lock the gang before rederiving the plan from current assignments.
        gang = Gang.objects.select_for_update().get(pk=gang_id)
        standing = dict(find(gang_id).gangs)
        if standing.get(gang_id) != ids:
            return (
                f"gang {gang_id}: skipped — its picks changed since the plan "
                "was read; read it again"
            )
        moved = 0
        for pick in Assignment.objects.select_for_update().filter(pk__in=ids):
            pick.miniature = None
            pick.gang = gang
            # Clear the previous model root before save derives the new gang host.
            pick.miniature_root = None
            pick.save()
            moved += 1
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
        f"gang {gang_id}: moved {moved} pick{'' if moved == 1 else 's'} onto the gang"
    )
