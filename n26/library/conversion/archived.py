"""The answers already taken back become picks too.

The conversions moved the answers a gang still holds. An answer taken
back is archived rather than deleted — a gang that changed its mind
keeps the row it dropped — and those were left where they were, still
naming the kind the system used to use.

Left alone they are the reason the old kinds cannot be retired: a kind
with rows pointing at it is a kind nothing may delete. This sweeps them
across by the same rewrite, so the last thing naming a retired kind
stops doing so.

**The proof is the story, and only the story.** An archived answer
draws nothing on any card, so no page can move whatever this does —
but the gang's history describes an old event by what its assignment
names *now*, and these assignments are what history is made of.
Rewriting one wrongly rewrites what a player is told they did. So
every affected gang's story is read before and after, and a word that
moves ends the run unless the plan said in advance that it would.

Exactly one wording does move, and the plan names it and counts it on
the page before anybody agrees to the run (``ALLOWED_REWORDS``). A
gang the plan did not name for it must read identically, so the
allowance cannot spread to a story it was not meant for.

Reading their pages as well would be the conversions' proof, and it is
the wrong one here twice over: it cannot fail, and it costs five times
what the story costs — a page is a second and a half of card building
against a third of a second of folding events, which over every gang
this touches is the difference between a transaction held for a minute
and one held for ten.

Which choice each answer settles is not written down anywhere: these
rows predate slots, so they name no slot and no offer. It is read from
the anchor instead. Every anchor that once carried an offer now grants
exactly one slot — that is what the conversions did to it — so the slot
an answer belongs to is the slot its own anchor grants. Anything that
does not resolve that way is refused by name rather than guessed at.
"""

from collections import Counter
from dataclasses import dataclass

from n26.library.conversion.base import ConversionRefused, Plan


@dataclass(frozen=True)
class RewriteArchivedAnswer:
    """One answer already taken back, re-said as a pick.

    Names what it settles on by identity rather than by name: a name
    belongs to a slot type, and two slot types can wear the same one —
    there is a Brawler among the specialisations and another among the
    archetypes, and a sweep crossing both systems must not confuse them.
    """

    assignment_id: object
    old_column: str
    pickable_id: object
    pickable_name: str
    slot_id: object
    slot_name: str
    gang: str

    def say(self):
        return (
            f"rewrite the archived {self.old_column} {self.assignment_id} "
            f"({self.gang}) -> “{self.pickable_name}” for “{self.slot_name}”"
        )

    def perform(self):
        """Write it, having proved again that it is what the plan read.

        The plan was read before this transaction opened. What it
        believed can have moved since — the answer claimed by something
        else, or brought back out of the archive — and a story read
        twice would not catch either, an archived answer's rewrite
        changing no word of one. So the row itself is checked here,
        where the snapshot holds.
        """
        from n26.core.models import Assignment
        from n26.library.conversion.base import ConversionRefused

        answer = Assignment.objects.get(pk=self.assignment_id)
        if not answer.archived:
            raise ConversionRefused(
                f"{self.assignment_id} is no longer an answer taken back"
            )
        if answer.pickable_id is not None or answer.chosen_for_slot_id is not None:
            raise ConversionRefused(
                f"{self.assignment_id} already names a pick, so something "
                "has rewritten it since the plan was read"
            )
        if getattr(answer, f"{self.old_column}_id") is None:
            raise ConversionRefused(
                f"{self.assignment_id} no longer names a {self.old_column}"
            )
        answer.pickable_id = self.pickable_id
        answer.chosen_for_id = answer.caused_by_id
        answer.chosen_for_slot_id = self.slot_id
        answer.chosen_for_offer = None
        setattr(answer, self.old_column, None)
        answer.save()


#: The columns the conversions emptied of live answers, in the order a
#: report reads best.
OLD_COLUMNS = ("specialisation", "archetype", "skill_tree")

#: The one change of wording this sweep may make, and nothing else.
#:
#: The archetype column holds two systems with nothing to do with each
#: other — the Outcast archetypes and the Venator gang legacies — so a
#: dropped legacy's history calls the house an "archetype". Said as the
#: pick it is, it says "gang legacy": the truthful word, and the one a
#: gang's kept legacies already use. Every other moved word is a
#: refusal, and so is any change to *what* arrived.
ALLOWED_REWORDS = (("archetype", "gang legacy"),)


@dataclass(frozen=True)
class ArchivedPlan(Plan):
    """The sweep's plan, carrying the rewording it has to own up to."""

    #: ``(old word, new word, how many answers)``, as the preview says it.
    rewords: tuple = ()
    #: The gangs whose stories may move. Every other gang's must not.
    reworded_gang_ids: tuple = ()

    def preview(self):
        lines = list(super().preview())
        for old, new, count in self.rewords:
            lines.insert(
                -1,
                f"[archived] {count} of those answer"
                f"{'' if count == 1 else 's'} will have their history say "
                f"“{new}” where it says “{old}” today",
            )
        return lines


def _slots_granted(assignable, seen):
    """The slots this thing's modifiers hand over, cached per plan."""
    key = (type(assignable).__name__, assignable.pk)
    if key not in seen:
        seen[key] = [
            modifier.adds_assignable.slot
            for modifier in assignable.modifiers.filter(
                adds_assignable__slot__isnull=False
            ).select_related(
                "adds_assignable__slot", "adds_assignable__slot__slot_type"
            )
        ]
    return seen[key]


def plan_archived():
    from n26.core.models import Assignment
    from n26.library.models import Pickable

    problems = []
    rows = []
    for column in OLD_COLUMNS:
        rows += list(
            Assignment.objects.filter(archived=True, **{f"{column}__isnull": False})
            .select_related(column, "caused_by", "gang_root")
            .order_by("created")
        )
    if not rows:
        return ArchivedPlan(system="archived", nothing_here=True)

    seen = {}
    steps = []
    reworded = []
    for row in rows:
        named = getattr(row, _column_of(row))
        cause = row.caused_by
        if cause is None:
            problems.append(f"archived answer {row.pk} hangs from nothing")
            continue
        anchor_thing = cause.assignable
        if anchor_thing is None:
            problems.append(
                f"archived answer {row.pk} hangs from an assignment naming nothing"
            )
            continue
        slots = _slots_granted(anchor_thing, seen)
        if len(slots) != 1:
            problems.append(
                f"“{anchor_thing}” grants {len(slots)} slots, so the answer "
                f"{row.pk} hanging from it cannot be placed"
            )
            continue
        slot = slots[0]
        # A name is unique per pack and qualifier, not per slot type, so
        # one slot type can hold two of a name. Either count but one is a
        # question this cannot answer.
        candidates = list(
            Pickable.objects.filter(slot_type=slot.slot_type, name=named.name)
        )
        if len(candidates) != 1:
            problems.append(
                f"{len(candidates)} things on “{slot.slot_type}” are called "
                f"“{named.name}”, which the archived answer {row.pk} names"
            )
            continue
        pickable = candidates[0]
        # What the history says about this answer today, and what it
        # would say once rewritten. Read with the history page's own
        # words rather than a copy of them, so the two cannot drift.
        was, becomes = _words(row), (str(pickable), slot.slot_type.name.lower())
        if was != becomes:
            if was[0] != becomes[0]:
                problems.append(
                    f"rewriting the archived answer {row.pk} would change "
                    f"what arrived from “{was[0]}” to “{becomes[0]}”"
                )
                continue
            if (was[1], becomes[1]) not in ALLOWED_REWORDS:
                problems.append(
                    f"rewriting the archived answer {row.pk} would have its "
                    f"history say “{becomes[1]}” where it says “{was[1]}”, "
                    "which is not a rewording this may make"
                )
                continue
            reworded.append(((was[1], becomes[1]), row.gang_root_id))
        steps.append(
            RewriteArchivedAnswer(
                assignment_id=row.pk,
                old_column=_column_of(row),
                pickable_id=pickable.pk,
                pickable_name=pickable.name,
                slot_id=slot.pk,
                slot_name=slot.name,
                gang=str(row.gang_root),
            )
        )

    if problems:
        return ArchivedPlan(system="archived", problems=tuple(problems))

    counted = Counter(pair for pair, _ in reworded)
    touched = sorted({row.gang_root_id for row in rows}, key=str)
    return ArchivedPlan(
        system="archived",
        steps=tuple(steps),
        gang_ids=tuple(touched),
        reaches=len(touched),
        rewords=tuple(
            (old, new, count) for (old, new), count in sorted(counted.items())
        ),
        reworded_gang_ids=tuple(sorted({gang for _, gang in reworded}, key=str)),
    )


def _words(row):
    """What the history page calls this row: its name, and its sort.

    The page's own functions, because the proof is about what a reader
    is told — a second implementation of the wording could agree with
    itself while disagreeing with the screen.
    """
    from n26.core.history import _kindword, _name

    return _name(row), _kindword(row)


def _column_of(row):
    for column in OLD_COLUMNS:
        if getattr(row, f"{column}_id") is not None:
            return column
    raise ValueError(f"{row.pk} names none of the old kinds")


def apply_archived(plan):
    """Rewrite every archived answer, and prove the stories unmoved.

    The conversions' own apply proves pages, which is the right proof
    for an answer a card draws. These draw nothing; what they hold up is
    the history, so that is what is read twice and compared.
    """
    from django.db import transaction

    from n26.core import history
    from n26.core.models import Gang
    from n26.core.reconcile import assert_reconciled
    from n26.library.conversion.base import _one_snapshot

    if plan.problems:
        raise ConversionRefused("[archived] not applied: " + "; ".join(plan.problems))
    if plan.nothing_here:
        return list(plan.preview())

    report = list(plan.preview())
    with _one_snapshot(), transaction.atomic():
        gangs = list(Gang.objects.filter(pk__in=plan.gang_ids))
        before_story = {str(gang.pk): _story(history.build(gang)) for gang in gangs}
        # Only the gangs the plan named may reword, and only in the way
        # it named. Everywhere else the story has to read identically,
        # so a coincidence somewhere unrelated cannot pass as expected.
        reworded = set(plan.reworded_gang_ids)

        for step in plan.steps:
            try:
                step.perform()
            except Exception as failed:
                raise ConversionRefused(
                    f"[archived] failed at “{step.say()}”: {failed}"
                ) from failed

        gangs = list(Gang.objects.filter(pk__in=plan.gang_ids))
        moved = []
        for gang in gangs:
            key = str(gang.pk)
            unexpected = _unexpected(
                before_story[key],
                _story(history.build(gang)),
                plan.rewords if gang.pk in reworded else (),
            )
            if unexpected:
                moved.append(
                    f"{gang}: the words its history tells have moved — "
                    + "; ".join(unexpected[:3])
                )
        if moved:
            raise ConversionRefused(
                "[archived] refused — what a reader is told would change:\n  "
                + "\n  ".join(moved)
            )
        for gang in gangs:
            try:
                assert_reconciled(gang)
            except Exception as failed:
                raise ConversionRefused(
                    f"[archived] refused — {gang} no longer reconciles: {failed}"
                ) from failed
    report.append(
        "[archived] rewritten; every story reads the same but for the "
        "rewording said above"
        if plan.rewords
        else "[archived] rewritten; every story reads the same"
    )
    return report


def _unexpected(before, after, rewords):
    """Every way two readings of a story disagree beyond what was said.

    A line may differ only by having one declared word put in place of
    another, and only on a gang the plan named. Anything else — a line
    gained or lost, a name changed, a word nobody declared — comes back
    as words, so a refusal says what it saw rather than that something
    happened.
    """
    if len(before) != len(after):
        return [f"the story is {len(before)} lines long and becomes {len(after)}"]
    found = []
    for was, now in zip(before, after, strict=True):
        if was == now:
            continue
        if any(was.replace(old, new) == now for old, new, _ in rewords):
            continue
        found.append(f"“{was}” -> “{now}”")
    return found


def _story(acts):
    """Every word a gang's history page puts on the screen."""
    told = []
    for act in acts:
        told.append("".join(span.text for span in act.spans))
        told.extend(f"{sub.name}|{sub.kind}|{sub.note}" for sub in act.subs)
    return told
