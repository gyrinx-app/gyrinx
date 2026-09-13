"""One-off planning and application for legacy earned action allowances."""

from dataclasses import dataclass
from itertools import groupby

from n26.core.access import actions_for, rank_table_for
from n26.core.allowances import grant_rank_allowances
from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import Assignment, Gang, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.core.reconcile import assert_reconciled


@dataclass(frozen=True)
class InitialisationPlan:
    gangs: tuple
    missing_baselines: tuple
    problems: tuple

    @property
    def nothing_here(self):
        return not self.gangs

    def preview(self):
        lines = [
            f"{len(self.gangs)} gang(s) contain legacy fighter counters to inspect.",
            f"{len(self.missing_baselines)} fighter counter(s) have no trustworthy starting value and will be skipped.",
        ]
        lines.extend(self.missing_baselines)
        return lines


def _candidate_assignments(gang=None):
    rows = Assignment.objects.filter(
        archived=False,
        counter__isnull=False,
        counter_value__isnull=False,
        miniature_root__membership__archived=False,
        miniature_root__membership__gang__archived=False,
    ).select_related(
        "counter",
        "counter_value",
        "materialised_from",
        "miniature_root__membership__gang",
    )
    return rows.filter(gang_root=gang) if gang is not None else rows


def _baselines(assignments):
    """Bulk-read original openings, then use only same-counter materialisation."""
    ids = [assignment.pk for assignment in assignments]
    openings = {
        event.assignment_id: event.counter_after
        for event in LedgerEvent.objects.filter(
            assignment_id__in=ids,
            kind=LedgerEvent.Kind.COUNTER_OPENED,
        )
        .order_by("assignment_id", "created", "pk")
        .distinct("assignment_id")
    }
    return {
        assignment.pk: openings.get(
            assignment.pk,
            (
                assignment.materialised_from.amount
                if assignment.materialised_from is not None
                and assignment.materialised_from.counter_id == assignment.counter_id
                else None
            ),
        )
        for assignment in assignments
    }


def _fighter_contexts(gang=None):
    assignments = list(
        _candidate_assignments(gang).order_by("miniature_root_id", "created", "pk")
    )
    baselines = _baselines(assignments)
    for _, grouped in groupby(assignments, key=lambda row: row.miniature_root_id):
        rows = list(grouped)
        fighter = rows[0].miniature_root
        card = build_card(fighter)
        computed = compute(card, build_modifier_index(carriers(card)))
        yield (
            fighter,
            rows,
            baselines,
            actions_for(fighter, card=card, computed=computed),
            card,
            computed,
        )


def find():
    """Build a dry-run plan without writing player history."""
    gangs = set()
    missing = []
    problems = []
    for (
        fighter,
        assignments,
        baselines,
        accesses,
        card,
        computed,
    ) in _fighter_contexts():
        for assignment in assignments:
            matching = [
                access.action
                for access in accesses
                if access.action.rank_allowance_rule_id
                and access.action.rank_allowance_rule.counter_id
                == assignment.counter_id
            ]
            if not matching:
                continue
            try:
                table = rank_table_for(
                    fighter, assignment.counter, card=card, computed=computed
                )
            except (Refusal, ValueError) as error:
                problems.append(f"{fighter} in {fighter.gang}: {error}")
                continue
            if table is None:
                continue
            gangs.add(fighter.membership.gang_id)
            if baselines[assignment.pk] is None:
                missing.append(
                    f"{fighter} in {fighter.gang}: {assignment.counter} has no original opening or matching materialised starting value."
                )
    return InitialisationPlan(
        gangs=tuple((pk,) for pk in sorted(gangs, key=str)),
        missing_baselines=tuple(missing),
        problems=tuple(problems),
    )


def apply_one(gang_id):
    """Reread and initialise one gang under its operation lock."""
    gang = Gang.objects.get(pk=gang_id, archived=False)
    assert_reconciled(gang)
    granted = skipped = 0
    with operation(gang, actor=None) as op:
        for (
            fighter,
            assignments,
            baselines,
            accesses,
            card,
            computed,
        ) in _fighter_contexts(gang):
            for assignment in assignments:
                matching = [
                    access.action
                    for access in accesses
                    if access.action.rank_allowance_rule_id
                    and access.action.rank_allowance_rule.counter_id
                    == assignment.counter_id
                ]
                if (
                    not matching
                    or rank_table_for(
                        fighter, assignment.counter, card=card, computed=computed
                    )
                    is None
                ):
                    continue
                baseline = baselines[assignment.pk]
                if baseline is None:
                    skipped += 1
                    continue
                granted += len(
                    grant_rank_allowances(
                        op, assignment, baseline, assignment.counter_value.value
                    )
                )
    gang.refresh_from_db()
    assert_reconciled(gang)
    return f"{gang}: granted {granted} earned use(s); skipped {skipped} counter(s) without a baseline."
