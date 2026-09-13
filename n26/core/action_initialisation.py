"""One-off planning and application for legacy earned action allowances."""

from dataclasses import dataclass

from n26.core.access import actions_for, rank_table_for
from n26.core.allowances import bootstrap_rank_allowances, starting_counter_value
from n26.core.models import Assignment, Gang
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


def find():
    """Build a dry-run plan without writing player history."""
    gangs = set()
    missing = []
    problems = []
    for assignment in _candidate_assignments().order_by("gang_root_id", "created"):
        fighter = assignment.miniature_root
        matching = [
            access.action
            for access in actions_for(fighter)
            if access.action.rank_allowance_rule_id
            and access.action.rank_allowance_rule.counter_id == assignment.counter_id
        ]
        if not matching:
            continue
        try:
            table = rank_table_for(fighter, assignment.counter)
        except (Refusal, ValueError) as error:
            problems.append(f"{fighter} in {fighter.gang}: {error}")
            continue
        if table is None:
            continue
        gangs.add(fighter.membership.gang_id)
        if starting_counter_value(assignment) is None:
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
        for assignment in _candidate_assignments(gang).order_by("created", "pk"):
            fighter = assignment.miniature_root
            matching = [
                access.action
                for access in actions_for(fighter)
                if access.action.rank_allowance_rule_id
                and access.action.rank_allowance_rule.counter_id
                == assignment.counter_id
            ]
            if not matching or rank_table_for(fighter, assignment.counter) is None:
                continue
            if starting_counter_value(assignment) is None:
                skipped += 1
                continue
            granted += len(bootstrap_rank_allowances(op, assignment))
    gang.refresh_from_db()
    assert_reconciled(gang)
    return f"{gang}: granted {granted} earned use(s); skipped {skipped} counter(s) without a baseline."
