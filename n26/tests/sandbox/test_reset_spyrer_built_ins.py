from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core import reset_spyrer_built_ins as reset
from n26.core.models import ActionRecord, Assignment, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library import authoring as a
from n26.library.models import DefaultAssignment
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(default_pack, owner, person_type, monkeypatch, counter_tracking):
    gang_type = a.create_gang_type("Spyre Hunters", starting_credits=1000)
    kills = a.create_counter("Kill Count")
    glitches = a.create_counter("Glitch Count")
    clear = a.create_outcome(
        "Clear glitches", a.apply_changes(a.counter_change(glitches, "set", 0))
    )
    action = a.create_action(
        "Suit Evolution",
        "post_cycle",
        outcomes=[clear],
        use_price=[
            {"resource": "counter", "payer": "fighter", "counter": kills, "amount": 4}
        ],
    )
    things = [
        a.create_rule("Fighter progression"),
        a.create_rule("Promotion"),
        action,
        a.create_action("Suit Maintenance", "post_cycle", outcomes=[clear]),
    ]
    members = [a.add_built_in(gang_type, thing) for thing in things]
    kept_rule = a.create_rule("Scions of the Imperial House")
    a.add_built_in(gang_type, kept_rule)
    gang_type.refresh_from_db()
    profile = a.create_profile("Jakara", person_type, gang_type, price=100)
    a.add_built_in(profile, kills, amount=4)
    a.add_built_in(profile, glitches, amount=3)
    gang = found_gang("Reset test", gang_type, owner=owner, budget=1000)
    fighter = hire(gang, profile, "Hunter")
    with operation(gang, actor=owner) as op:
        cancelled = op.start_action(fighter, action, uuid4())
        cancelled = op.cancel_action(cancelled)
        completed = op.start_action(fighter, action, uuid4())
        completed = op.review_action(completed, outcome=clear)
        completed = op.complete_action(
            completed,
            outcome=clear,
            revision=completed.revision,
            review=completed.review,
        )
        draft = op.start_action(fighter, action, uuid4())
    monkeypatch.setattr(reset, "GANG_TYPE_ID", str(gang_type.pk))
    monkeypatch.setattr(reset, "DEFAULT_SET_ID", str(gang_type.built_ins_id))
    monkeypatch.setattr(
        reset,
        "MEMBERS",
        {
            str(member.pk): ("rule" if member.rule_id else "action", str(thing.pk))
            for member, thing in zip(members, things, strict=True)
        },
    )
    monkeypatch.setattr(
        reset, "USES", {str(row.pk): row.state for row in [cancelled, completed, draft]}
    )
    return SimpleNamespace(
        gang=gang,
        gang_type=gang_type,
        fighter=fighter,
        action=action,
        clear=clear,
        members=members,
        kept_rule=kept_rule,
        profile=profile,
        kills=kills,
        glitches=glitches,
        records=[cancelled, completed, draft],
    )


def test_preview_does_not_write_and_reset_removes_only_the_measured_setup(setup):
    with CaptureQueriesContext(connection) as queries:
        plan = reset.find()
    assert plan.ok, plan.problems
    assert plan.uses == 3
    assert len(plan.members) == 4
    assert len(plan.gangs[0][1]) == 4
    assert not any(
        query["sql"].lstrip().startswith(("UPDATE", "DELETE", "INSERT"))
        for query in queries
    )
    before = (setup.gang.rating, setup.gang.credits)
    reset.prepare()
    assert not DefaultAssignment.objects.filter(
        pk__in=reset.MEMBERS, archived=False
    ).exists()
    reset.apply_one(setup.gang.pk)
    assert not Assignment.objects.filter(
        materialised_from_id__in=reset.MEMBERS
    ).exists()
    assert not DefaultAssignment.objects.filter(pk__in=reset.MEMBERS).exists()
    assert not ActionRecord.objects.filter(pk__in=reset.USES).exists()
    assert not LedgerEvent.objects.filter(action_record_id__in=reset.USES).exists()
    assert Assignment.objects.filter(gang=setup.gang, rule=setup.kept_rule).exists()
    balances = dict(
        Assignment.objects.filter(
            miniature_root=setup.fighter, counter__isnull=False
        ).values_list("counter__name", "counter_value__value")
    )
    assert balances == {"Kill Count": 4, "Glitch Count": 3}
    setup.gang.refresh_from_db()
    assert (setup.gang.rating, setup.gang.credits) == before
    assert reset.find().nothing_here
    assert reset.prepare().nothing_here
    reset.apply_one(setup.gang.pk)
    assert_reconciled(setup.gang)


def test_reset_refuses_a_counter_movement_after_the_inspected_use(setup):
    balance = Assignment.objects.get(miniature_root=setup.fighter, counter=setup.kills)
    with operation(setup.gang, actor=setup.gang.owner) as op:
        op.tally(balance, 1)
    assert not reset.find().ok
    with pytest.raises(reset.Refused, match="changed after"):
        reset.prepare()
    assert (
        DefaultAssignment.objects.filter(pk__in=reset.MEMBERS, archived=False).count()
        == 4
    )


def test_the_inspected_later_manual_tallies_keep_their_deltas(setup, monkeypatch):
    balance = Assignment.objects.get(miniature_root=setup.fighter, counter=setup.kills)
    with operation(setup.gang, actor=setup.gang.owner) as op:
        op.tally(balance, 1)
    event = LedgerEvent.objects.filter(assignment=balance).latest("created")
    monkeypatch.setattr(reset, "LATER_TALLIES", {str(event.pk)})
    assert reset.find().ok
    reset.prepare()
    reset.apply_one(setup.gang.pk)
    event.refresh_from_db()
    assert (event.counter_before, event.counter_after, event.counter_delta) == (4, 5, 1)
    assert balance.counter_value.value == 5
    assert_reconciled(setup.gang)


def test_reset_refuses_an_additional_action_use(setup):
    another = hire(setup.gang, setup.profile, "Second Hunter")
    with operation(setup.gang, actor=setup.gang.owner) as op:
        extra = op.start_action(another, setup.action, uuid4())
    assert str(extra.pk) not in reset.USES
    assert extra.source_assignment_id in Assignment.objects.filter(
        materialised_from_id__in=reset.MEMBERS
    ).values_list("pk", flat=True)
    assert not reset.find().ok
    with pytest.raises(reset.Refused, match="changed since"):
        reset.apply_one(setup.gang.pk)
    assert (
        Assignment.objects.filter(materialised_from_id__in=reset.MEMBERS).count() == 4
    )


def test_reset_refuses_dependent_equipment(setup):
    source = Assignment.objects.filter(materialised_from_id__in=reset.MEMBERS).first()
    gear = a.create_wargear("Unrelated gear")
    with operation(setup.gang, actor=setup.gang.owner) as op:
        op.assign(gear, miniature=setup.fighter, caused_by=source)
    assert not reset.find().ok
    with pytest.raises(reset.Refused, match="dependent equipment"):
        reset.apply_one(setup.gang.pk)


def test_unrelated_action_uses_are_kept(setup):
    other = a.create_action("Unrelated action", "post_cycle", outcomes=[setup.clear])
    with operation(setup.gang, actor=setup.gang.owner) as op:
        op.assign(other, miniature=setup.fighter)
        record = op.start_action(setup.fighter, other, uuid4())
    reset.prepare()
    reset.apply_one(setup.gang.pk)
    assert ActionRecord.objects.filter(pk=record.pk).exists()


def test_an_interrupted_run_can_resume_and_new_gangs_do_not_receive_the_setup(
    setup, owner
):
    another = found_gang("Another", setup.gang_type, owner=owner, budget=1000)
    plan = reset.prepare()
    assert len(plan.gangs) == 2
    reset.apply_one(setup.gang.pk)
    assert DefaultAssignment.objects.filter(pk__in=reset.MEMBERS).count() == 4
    later = found_gang("Later", setup.gang_type, owner=owner, budget=1000)
    assert not Assignment.objects.filter(
        gang=later, materialised_from_id__in=reset.MEMBERS
    ).exists()
    assert len(reset.prepare().gangs) == 1
    reset.apply_one(another.pk)
    assert reset.find().nothing_here


def test_failure_rolls_back_deleted_records_and_restored_counters(setup, monkeypatch):
    from n26.core import reconcile

    check = reconcile.assert_reconciled
    calls = 0

    def fail_after(gang):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Failed after deletion")
        check(gang)

    monkeypatch.setattr(reconcile, "assert_reconciled", fail_after)
    with pytest.raises(RuntimeError, match="Failed after deletion"):
        reset.apply_one(setup.gang.pk)
    assert ActionRecord.objects.filter(pk__in=reset.USES).count() == 3
    assert (
        Assignment.objects.filter(materialised_from_id__in=reset.MEMBERS).count() == 4
    )
    assert DefaultAssignment.objects.filter(pk__in=reset.MEMBERS).count() == 4
    assert not reset.find().problems
