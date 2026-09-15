import pytest

from n26.core.allowances import (
    bootstrap_rank_allowances,
    grant_rank_allowances,
    grant_recruitment_allowances,
    starting_counter_value,
)
from n26.core.models import ActionAllowance, Gang, LedgerEvent
from n26.core.operations import operation
from n26.library.models import (
    Action,
    Counter,
    RankAllowanceRule,
    RankTable,
    RankThreshold,
    RecruitmentAllowanceRule,
)

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def fighter(user, gang_type, make_profile, make_statline):
    gang = Gang.objects.create(name="The Hunt", owner=user, gang_type=gang_type)
    profile = make_profile("Hunter", price=100)
    make_statline(profile)
    with operation(gang, actor=user) as op:
        return op.hire(profile, "Kara", paid=100)


def test_recruitment_allowances_are_granted_once_after_access_exists(fighter):
    rule = RecruitmentAllowanceRule.objects.create()
    action = Action.objects.create(
        name="Recruitment augmentation",
        timing="recruitment",
        recruitment_allowance_rule=rule,
    )
    with operation(fighter.membership.gang) as op:
        op.assign(action, miniature=fighter)
        assert len(grant_recruitment_allowances(op, fighter)) == 1
        assert grant_recruitment_allowances(op, fighter) == []
    allowance = ActionAllowance.objects.get()
    assert allowance.recruitment == fighter.membership
    assert allowance.granted_event.kind == LedgerEvent.Kind.GRANTED


def test_rank_allowances_grant_only_strict_crossings_and_never_regrant(fighter):
    xp = Counter.objects.create(name="XP")
    table = RankTable.objects.create(name="Standard ranks", counter=xp)
    for value in (4, 7, 10):
        RankThreshold.objects.create(rank_table=table, threshold=value)
    rule = RankAllowanceRule.objects.create(counter=xp)
    action = Action.objects.create(
        name="Advancement", timing="post_cycle", rank_allowance_rule=rule
    )
    with operation(fighter.membership.gang) as op:
        op.assign(action, miniature=fighter)
        op.assign(table, miniature=fighter)
        counter_assignment = op.assign(xp, miniature=fighter)
        op.open_counter(counter_assignment, 0)
        assert [
            a.threshold for a in grant_rank_allowances(op, counter_assignment, 3, 8)
        ] == [4, 7]
        assert grant_rank_allowances(op, counter_assignment, 8, 3) == []
        assert grant_rank_allowances(op, counter_assignment, 3, 8) == []
    assert not ActionAllowance.objects.filter(granted_event__isnull=True).exists()


def test_bootstrap_requires_a_real_opening_and_uses_it_as_the_lower_bound(fighter):
    xp = Counter.objects.create(name="XP")
    table = RankTable.objects.create(name="Standard ranks", counter=xp)
    RankThreshold.objects.create(rank_table=table, threshold=7)
    rule = RankAllowanceRule.objects.create(counter=xp)
    action = Action.objects.create(
        name="Advancement", timing="post_cycle", rank_allowance_rule=rule
    )
    with operation(fighter.membership.gang) as op:
        op.assign(action, miniature=fighter)
        op.assign(table, miniature=fighter)
        counter_assignment = op.assign(xp, miniature=fighter)
        assert starting_counter_value(counter_assignment) is None
        assert bootstrap_rank_allowances(op, counter_assignment) == []
        held = op.open_counter(counter_assignment, 6)
        held.value = 8
        held.save(update_fields=["value"])
        assert [
            a.threshold for a in bootstrap_rank_allowances(op, counter_assignment)
        ] == [7]
        LedgerEvent.objects.filter(assignment=counter_assignment).update(
            kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED
        )
        assert starting_counter_value(counter_assignment) is None


def test_clone_copies_only_unused_allowances(fighter):
    rule = RecruitmentAllowanceRule.objects.create()
    action = Action.objects.create(
        name="Recruitment augmentation",
        timing="recruitment",
        recruitment_allowance_rule=rule,
    )
    unused = ActionAllowance.objects.create(
        action=action,
        fighter=fighter,
        recruitment=fighter.membership,
        source_kind=ActionAllowance.Source.RECRUITMENT,
    )
    with operation(fighter.gang) as op:
        clone = op.clone_miniature(fighter)
    copied = clone.action_allowances.get()
    assert copied.action == unused.action
    assert copied.recruitment == clone.membership
    assert copied.granted_event.kind == LedgerEvent.Kind.GRANTED
