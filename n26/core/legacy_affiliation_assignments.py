"""Delete the last player assignments left by the Affiliation conversions.

The conversions deliberately preserved two kinds of old row.  Variant's
``None`` assignment was archived so an optional slot would still read as
unanswered, and a doubled Outcast assignment was left as a spare when another
assignment already settled the question.  Both still point at the retired
Affiliation library rows and therefore keep those rows from being deleted.

This is a deliberately narrow repair.  It recognises only the two shapes
measured in production, proves that their books are empty and that nothing
depends on them, then deletes the assignment together with its ledger entry
and history events.  Every affected gang must reconcile; an archived assignment
must render identically, while a live spare may remove only its own obsolete
line from the gang sheet.
"""

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from n26.core.capture import differences, gang_state

ARCHIVED_NONE = "archived None"
LIVE_SPARE = "live spare"


class Refused(Exception):
    """The repair found something other than the measured legacy shapes."""


@dataclass(frozen=True)
class LegacyAffiliationAssignments:
    """Assignments safe to delete, grouped by their gang."""

    #: ``(gang id, ((assignment id, classification), ...))``.
    gangs: tuple = ()
    problems: tuple = ()
    nothing_here: bool = False

    @property
    def ok(self):
        return not self.problems

    @property
    def assignment_ids(self):
        return tuple(pk for _, rows in self.gangs for pk, _ in rows)

    def preview(self):
        lines = []
        if self.nothing_here:
            lines.append("no legacy affiliation assignments remain")
        for gang_id, rows in self.gangs:
            counts = {
                kind: sum(found == kind for _, found in rows)
                for kind in (ARCHIVED_NONE, LIVE_SPARE)
            }
            parts = []
            if counts[ARCHIVED_NONE]:
                count = counts[ARCHIVED_NONE]
                parts.append(
                    f"{count} archived None assignment{'' if count == 1 else 's'}"
                )
            if counts[LIVE_SPARE]:
                count = counts[LIVE_SPARE]
                parts.append(
                    f"{count} live spare assignment{'' if count == 1 else 's'}"
                )
            lines.append(f"gang {gang_id}: delete " + " and ".join(parts))
        if self.gangs:
            count = len(self.assignment_ids)
            lines.append(
                f"{count} assignment{'' if count == 1 else 's'} across "
                f"{len(self.gangs)} gang{'' if len(self.gangs) == 1 else 's'}; "
                "their zero-value ledger entries and history events are deleted too"
            )
        return lines


def _problem(assignment, reason):
    return f"assignment {assignment.pk} naming “{assignment.affiliation}” {reason}"


def _has_unexpected_dependants(assignment):
    """Relations whose cascade would delete anything except empty books."""
    from n26.core.models import Assignment

    checks = (
        (assignment.children, "child assignments"),
        (assignment.caused, "caused assignments"),
        (assignment.picks, "picks"),
        (assignment.assignment_sets, "model-card sets"),
        (assignment.print_configs, "print configurations"),
        (assignment.chosen_options, "chosen profile options"),
    )
    found = [label for manager, label in checks if manager.exists()]
    for relation, label in (
        ("founded", "a founded gang"),
        ("member", "a model membership"),
        ("profile_role", "a profile role"),
        ("counter_value", "a counter value"),
    ):
        try:
            getattr(assignment, relation)
        except assignment._meta.get_field(relation).related_model.DoesNotExist:
            pass
        else:
            found.append(label)
    if Assignment.objects.filter(materialised_for=assignment).exists():
        found.append("materialised assignments")
    return found


def _empty_books(assignment, *, allowed_events):
    try:
        entry = assignment.ledger_entry
    except assignment._meta.get_field("ledger_entry").related_model.DoesNotExist:
        return "has no ledger entry"
    if (
        entry.list_price,
        entry.discount,
        entry.paid,
        entry.trade_points,
        entry.rating_contribution,
    ) != (0, 0, 0, 0, 0):
        return "has a non-zero ledger entry"
    if entry.reason != "granted" or entry.bought_from_id is not None:
        return "does not have the zero-value granted ledger shape"

    events = list(assignment.ledger_events.order_by("created", "id"))
    if any(event.gang_id != assignment.gang_root_id for event in events):
        return "has a history event pinned to another gang"
    if tuple(event.kind for event in events) not in allowed_events:
        return "does not have the measured granted/removed history"
    if any(
        (event.credits_delta, event.trade_points_delta, event.rating_delta) != (0, 0, 0)
        for event in events
    ):
        return "has a non-zero history event"
    return ""


def _common_problem(assignment):
    affiliation = assignment.affiliation
    if affiliation.pack.slug != settings.DEFAULT_CONTENT_PACK_SLUG:
        return "belongs to another content pack"
    if affiliation.modifiers.exists():
        return "names an affiliation that still carries modifiers"
    if affiliation.built_ins_id is not None and affiliation.built_ins.members.exists():
        return "names an affiliation whose built-in set is not empty"
    if assignment.removes:
        return "is a removal"
    if (
        assignment.gang_id is None
        or assignment.miniature_id is not None
        or assignment.parent_id is not None
        or assignment.stash_id is not None
        or assignment.gang_root_id != assignment.gang_id
        or assignment.miniature_root_id is not None
        or assignment.stash_root_id is not None
    ):
        return "is not hosted and rooted directly on one gang"
    if assignment.caused_by_id is None or assignment.caused_by.archived:
        return "does not name a live cause"
    if assignment.caused_by.gang_root_id != assignment.gang_root_id:
        return "does not share its cause's gang root"
    if any(
        (
            assignment.chosen_for_id,
            assignment.chosen_for_slot_id,
            assignment.chosen_for_offer_id,
            assignment.materialised_from_id,
            assignment.materialised_for_id,
        )
    ):
        return "still carries choice or materialisation provenance"
    dependants = _has_unexpected_dependants(assignment)
    if dependants:
        return "still has " + ", ".join(dependants)
    return ""


def _archived_none_problem(assignment):
    if not assignment.archived:
        return "is a live None assignment"
    if assignment.caused_by.gang_type_id is None:
        return "was not caused by the gang-type assignment"
    books = _empty_books(
        assignment,
        allowed_events=(("granted",), ("granted", "removed")),
    )
    if books:
        return books
    grant_modifiers = assignment.caused_by.gang_type.modifiers.filter(
        adds_assignable__slot__name="Variant",
        adds_assignable__slot__slot_type__name="Variant",
        adds_assignable__slot__pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG,
        targets_gang__isnull=False,
    )
    if grant_modifiers.count() != 1:
        return "does not have one Variant-slot grant on its gang-type cause"
    return ""


def _live_spare_problem(assignment):
    if assignment.archived:
        return "is an archived non-None assignment"
    if assignment.caused_by.hidden_id is None:
        return "was not caused by the old “Affiliation” marker"
    books = _empty_books(assignment, allowed_events=(("granted",),))
    if books:
        return books

    from n26.core.models import Assignment

    siblings = Assignment.objects.filter(
        gang_root_id=assignment.gang_root_id,
        gang_id=assignment.gang_root_id,
        caused_by_id=assignment.caused_by_id,
        chosen_for_id=assignment.caused_by_id,
        chosen_for_slot__slot_type__name="Affiliation",
        chosen_for_slot__name="Affiliation",
        pickable__isnull=False,
    )
    matching_old = siblings.filter(
        archived=True,
        pickable__name=assignment.affiliation.name,
    )
    current = siblings.filter(archived=False)
    if matching_old.count() != 1 or current.count() != 1:
        return (
            "does not have one archived converted pick of the same name and "
            "one live pick settling the “Affiliation” slot"
        )
    return ""


def find(gang_id=None):
    """Read the exact legacy assignments that may be deleted."""
    from n26.core.models import Assignment

    rows = Assignment.objects.filter(affiliation__isnull=False)
    if gang_id is not None:
        rows = rows.filter(gang_root_id=gang_id)
    rows = rows.select_related(
        "affiliation__pack",
        "affiliation__built_ins",
        "caused_by",
    ).order_by("gang_root_id", "created", "id")

    problems = []
    by_gang = {}
    for assignment in rows:
        problem = _common_problem(assignment)
        classification = None
        if not problem and assignment.affiliation.name == "None":
            classification = ARCHIVED_NONE
            problem = _archived_none_problem(assignment)
        elif not problem:
            classification = LIVE_SPARE
            problem = _live_spare_problem(assignment)
        if problem:
            problems.append(_problem(assignment, problem))
            continue
        by_gang.setdefault(assignment.gang_root_id, []).append(
            (assignment.pk, classification)
        )

    gangs = tuple(
        (pk, tuple(assignments))
        for pk, assignments in sorted(by_gang.items(), key=lambda item: item[0])
    )
    return LegacyAffiliationAssignments(
        gangs=gangs,
        problems=tuple(problems),
        nothing_here=not gangs and not problems,
    )


def apply(plan):
    """Delete the planned rows gang by gang, refusing an unsafe plan."""
    if plan.problems:
        raise Refused(
            "The deletion cannot run because " + "; ".join(plan.problems) + "."
        )
    if plan.nothing_here:
        return list(plan.preview())

    report = list(plan.preview())
    for gang_id, assignments in plan.gangs:
        report.append(_delete_one(gang_id, assignments))
    return report


def _delete_one(gang_id, assignments):
    from copy import deepcopy

    from n26.core.models import Assignment, Gang
    from n26.core.reconcile import check_gang

    ids = tuple(pk for pk, _ in assignments)
    with transaction.atomic():
        gang = Gang.objects.select_for_update().get(pk=gang_id)
        locked = list(
            Assignment.objects.select_for_update().filter(pk__in=ids).order_by("pk")
        )
        standing = dict(find(gang_id).gangs)
        if standing.get(gang_id) != assignments:
            return (
                f"gang {gang_id}: skipped — its affiliation assignments changed "
                "since the plan was read; run the deletion again with a new plan"
            )

        before_problems = check_gang(gang)
        if before_problems:
            return (
                f"gang {gang_id}: skipped — it did not reconcile before the "
                "deletion: " + "; ".join(before_problems)
            )
        before = gang_state(gang)
        expected = deepcopy(before)
        kinds = dict(assignments)
        for assignment in locked:
            if kinds[assignment.pk] == LIVE_SPARE:
                try:
                    expected["rows"].remove(str(assignment.affiliation))
                except ValueError:
                    return (
                        f"gang {gang_id}: skipped — live spare assignment "
                        f"{assignment.pk} has no matching gang-sheet line"
                    )
        Assignment.objects.filter(pk__in=ids).delete()
        gang.refresh_from_db()
        after_problems = check_gang(gang)
        changed = differences(expected, gang_state(gang))
        if after_problems or changed:
            transaction.set_rollback(True)
            reasons = []
            if after_problems:
                reasons.append(
                    "its books no longer reconcile: " + "; ".join(after_problems)
                )
            if changed:
                reasons.append(
                    "its pages would change beyond removing the live spare line: "
                    + "; ".join(changed)
                )
            return f"gang {gang_id}: skipped — " + "; ".join(reasons)

    count = len(ids)
    return (
        f"gang {gang_id}: deleted {count} legacy assignment{'' if count == 1 else 's'}"
    )
