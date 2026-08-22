"""The answers a doubled click left behind.

A question answered twice in the same moment left two rows where one
belongs: the picker settled the question from the page it had drawn, so
two answers in flight together each found nothing to replace. The second
row settles nothing — the question already reads as answered by its
sibling — but it is still an assignment naming a thing, so the model's
gear list draws a line for it.

That line is the whole of what a player sees, and it is wrong: it names
a sort of question, not a thing anybody owns. Nothing follows from the
row otherwise. What it grants arrives once regardless, because the
sibling grants it too; it was never paid for and adds nothing to what
the gang is worth.

Clearing one deletes it. It is not history — an answer taken back is
archived and kept, and these were never taken back — so there is nothing
to preserve, and leaving them archived instead would only hand the same
rows to a sweep that would faithfully make two picks out of them.

**The proof is the page, minus exactly the lines named.** Every other
deletion in this programme proves that nothing a reader sees moves;
this one is meant to move something, so it says which lines beforehand
and holds itself to removing those and nothing else. A gang whose page
changes in any other way ends the run.
"""

from dataclasses import dataclass

from django.db import transaction


class Refused(Exception):
    """The world is not the one the clearing read."""


@dataclass(frozen=True)
class Spare:
    """One row too many, and the line it draws."""

    assignment_id: object
    gang_id: object
    model_id: str
    model_said: str
    gang_said: str
    line_name: str
    line_rating: object

    def say(self):
        return (
            f"clear the spare “{self.line_name}” from {self.model_said} "
            f"({self.gang_said})"
        )


@dataclass(frozen=True)
class Spares:
    """What stands, and what clearing it would take off the page."""

    found: tuple = ()
    problems: tuple = ()
    nothing_here: bool = False

    @property
    def ok(self):
        return not self.problems

    @property
    def gang_ids(self):
        return tuple(sorted({spare.gang_id for spare in self.found}, key=str))

    def preview(self):
        if self.nothing_here:
            return ["nothing to clear — no question is answered twice over"]
        lines = [spare.say() for spare in self.found]
        lines.append(
            f"prove {len(self.gang_ids)} gang"
            f"{'' if len(self.gang_ids) == 1 else 's'} read the same but for "
            f"those {len(self.found)} line"
            f"{'' if len(self.found) == 1 else 's'}, or refuse"
        )
        return lines


def find():
    """Read the spares as they stand. Never writes."""
    from n26.core.capture import gang_state
    from n26.core.models import Assignment, Gang
    from n26.library.conversion.archived import OLD_COLUMNS

    live = Assignment.objects.filter(archived=False).exclude(removes=True)
    rows = []
    for column in OLD_COLUMNS:
        rows += list(
            live.filter(**{f"{column}__isnull": False})
            .select_related(column, "caused_by", "gang_root", "miniature_root")
            .order_by("created")
        )
    if not rows:
        return Spares(nothing_here=True)

    problems = []
    found = []
    pages = {}
    candidates = {}
    for row in rows:
        named = row.assignable
        if named is None:
            problems.append(f"the spare {row.pk} names nothing")
            continue
        if row.caused_by_id is None:
            problems.append(f"the spare {row.pk} hangs from nothing")
            continue
        # A spare is only spare because the question it answers is
        # already settled. Without a sibling standing it is the answer,
        # and clearing it would take a player's choice away.
        settled = live.filter(
            caused_by_id=row.caused_by_id, chosen_for_slot__isnull=False
        )
        if not settled.exists():
            problems.append(
                f"nothing else answers what the spare {row.pk} answers, so "
                "it is the answer rather than a spare"
            )
            continue
        hanging = (
            Assignment.objects.filter(caused_by=row)
            | Assignment.objects.filter(chosen_for=row)
            | Assignment.objects.filter(parent=row)
        )
        if hanging.exists():
            problems.append(f"something hangs off the spare {row.pk}")
            continue
        carried = _what_it_carries(row)
        if carried:
            problems.append(f"the spare {row.pk} carries {carried}")
            continue
        if row.miniature_root_id is None:
            problems.append(f"the spare {row.pk} sits on no model")
            continue

        gang = row.gang_root
        if gang.pk not in pages:
            pages[gang.pk] = gang_state(Gang.objects.get(pk=gang.pk))
        if str(row.miniature_root_id) not in pages[gang.pk]["models"]:
            problems.append(f"the spare {row.pk} sits on no model the sheet draws")
            continue
        candidates.setdefault(
            (gang.pk, str(row.miniature_root_id), str(named)), []
        ).append(row)

    # Which lines go is settled per model and name rather than per row,
    # because a click that landed three times leaves three rows drawing
    # three identical lines. The rule is that the page draws exactly as
    # many as there are spares to account for them: one more and
    # something a player owns shares the name, which is not this to
    # delete.
    for (gang_id, model_id, name), rows_here in sorted(
        candidates.items(), key=lambda pair: str(pair[0])
    ):
        drawn = pages[gang_id]["models"][model_id]
        matching = [line for line in drawn["equipment"] if line[0] == name]
        first = rows_here[0]
        if len(matching) != len(rows_here):
            problems.append(
                f"{len(matching)} lines on {first.miniature_root} are called "
                f"“{name}” and {len(rows_here)} spares name it, so which "
                "lines would go is not settled"
            )
            continue
        for row, (line_name, line_rating) in zip(rows_here, matching, strict=True):
            found.append(
                Spare(
                    assignment_id=row.pk,
                    gang_id=gang_id,
                    model_id=model_id,
                    model_said=str(row.miniature_root),
                    gang_said=str(row.gang_root),
                    line_name=line_name,
                    line_rating=line_rating,
                )
            )

    if problems:
        return Spares(problems=tuple(problems))
    return Spares(found=tuple(found))


def _what_it_carries(row):
    """Money or worth hanging on this row, in words — empty if none.

    A spare that was paid for or that counts towards what the gang is
    worth is not a spare: clearing it would move a number a player
    reads, and the money is somebody's to decide about, not this.
    """
    from n26.core.models import LedgerEntry

    entry = LedgerEntry.objects.filter(assignment=row).first()
    if entry is None:
        return ""
    said = []
    if entry.paid:
        said.append(f"{entry.paid} credits paid")
    if entry.rating_contribution:
        said.append(f"{entry.rating_contribution} of the gang's worth")
    return " and ".join(said)


def apply(spares):
    """Clear exactly the spares named, and prove the pages otherwise whole."""
    from n26.core.capture import differences, gang_state
    from n26.core.models import Assignment, Gang
    from n26.core.reconcile import assert_reconciled
    from n26.library.conversion.base import _one_snapshot

    if spares.problems:
        raise Refused("not cleared: " + "; ".join(spares.problems))
    if spares.nothing_here:
        return list(spares.preview())

    report = list(spares.preview())
    with _one_snapshot(), transaction.atomic():
        gangs = list(Gang.objects.filter(pk__in=spares.gang_ids))
        before = {str(gang.pk): gang_state(gang) for gang in gangs}
        want = _without_those_lines(before, spares)

        # The history events describing these rows ride the deletion:
        # ``LedgerEvent.assignment`` cascades. There is no story to keep
        # — a click that landed twice is not something a player did
        # twice.
        deleted, _ = Assignment.objects.filter(
            pk__in=[spare.assignment_id for spare in spares.found]
        ).delete()
        if not deleted:
            raise Refused("refused — nothing was there to clear")

        gangs = list(Gang.objects.filter(pk__in=spares.gang_ids))
        after = {str(gang.pk): gang_state(gang) for gang in gangs}
        changed = differences(want, after)
        if changed:
            raise Refused(
                "refused — the pages changed in ways this did not say they "
                "would:\n  " + "\n  ".join(changed[:10])
            )
        for gang in gangs:
            try:
                assert_reconciled(gang)
            except Exception as failed:
                raise Refused(
                    f"refused — {gang} no longer reconciles: {failed}"
                ) from failed
    report.append("cleared; every page reads the same but for those lines")
    return report


def _without_those_lines(before, spares):
    """The pages as they should read once the spares are gone.

    Built from what was captured rather than from what is found
    afterwards, so the run is held to the lines it named: anything else
    that moves shows up as a difference instead of being absorbed.
    """
    import copy

    want = copy.deepcopy(before)
    for spare in spares.found:
        gang = want[str(spare.gang_id)]
        lines = gang["models"][spare.model_id]["equipment"]
        line = (spare.line_name, spare.line_rating)
        if line not in lines:
            raise Refused(
                f"refused — the line “{spare.line_name}” the plan named is "
                f"no longer on {spare.model_said}"
            )
        lines.remove(line)
    return want
