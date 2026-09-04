"""Moving a gang's picks off the models they were written on.

A slot sets where its pick lands: on the bearer, or on the gang where
the slot is the Leader-picks-for-the-gang arrow. The Outcast Archetype
slot is that arrow — the Leader is asked, the gang holds the pick, and
it reaches every member through the gang. A pick is hosted where the
slot pointed at the moment it was made, and changing the slot moves
nothing already written: a pick made while the slot pointed at the
bearer sits on the Leader, and a gang whose pick sits on its Leader
reads differently from one whose pick sits on the gang.

The repair finds every live pick whose slot points at the gang and which
sits on a model, and moves it onto the model's gang. Nothing else about the
pick changes: it still names the assignment that asked and the slot it
settles, so the Leader's card still reads it as chosen, and it is still
caused by the Leader's hire, so it still goes when the Leader does.
Anything the pick caused — a power taken through what it offered — is
hosted in its own right and stays where it is.

An archived pick on a model is counted and left alone: it draws nothing,
and moving history is not a repair. Nothing here moves money: every
pick's entry pins zero, so the books fold as they did, and each gang is
proved to reconcile before its move commits.
"""

from dataclasses import dataclass

from django.db import transaction


class Refused(Exception):
    """The repair found something other than the fault it was written for."""


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
    """Whether the choice this pick settles was the model's own to make.

    A slot pointing at the gang can still put its pick on a model on
    purpose: a choice the gang carries for each of its members rides
    every card, and settling it names the fighter whose card was
    clicked, so that fighter's pick is theirs alone. Such a pick is not
    stray, and hoisting it onto the gang would make one fighter's choice
    everyone's. The two are told apart by what asked: a stray pick was
    asked by the model's own line (its membership, or something it
    carries), a deliberate one by a line the gang carries that is about
    nobody in particular.
    """
    asked = pick.chosen_for
    if asked is None:
        return False
    if asked.miniature_root_id is not None:
        return asked.miniature_root_id == pick.miniature_id
    return False


def find(gang_id=None):
    """What stands to be moved, gang by gang. ``gang_id`` narrows the
    plan to that one gang."""
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
    """Move what the plan names, gang by gang, and prove each gang's
    books whole.

    Each gang is its own transaction: one that cannot be made whole is
    left exactly as it stood and reported, and the rest are repaired.
    """
    if astray.problems:
        raise Refused("not moved: " + "; ".join(astray.problems))
    if astray.nothing_here:
        return list(astray.preview())

    report = list(astray.preview())
    for gang_id, ids in astray.gangs:
        report.append(_rehost_one(gang_id, ids))
    return report


def _rehost_one(gang_id, ids):
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
        if standing.get(gang_id) != ids:
            return (
                f"gang {gang_id}: skipped — its picks changed since the plan "
                "was read; read it again"
            )
        moved = 0
        for pick in Assignment.objects.select_for_update().filter(pk__in=ids):
            pick.miniature = None
            pick.gang = gang
            # save() derives the gang root from the host and leaves the
            # model root alone, so the old one is cleared here: a pick
            # the gang holds is about nobody in particular.
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
