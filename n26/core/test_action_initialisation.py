from contextlib import contextmanager
from uuid import uuid4

import pytest
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from n26 import maintenance
from n26.core import action_initialisation, allowances
from n26.core.action_initialisation import apply_one, find
from n26.core.models import ActionAllowance, Gang, LedgerEvent
from n26.core.operations import operation
from n26.library.models import (
    Action,
    Counter,
    RankAllowanceRule,
    RankTable,
    RankThreshold,
)

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def legacy_fighter(user, gang_type, make_profile, make_statline):
    gang = Gang.objects.create(name="Legacy", owner=user, gang_type=gang_type)
    profile = make_profile("Hunter", price=100)
    make_statline(profile)
    with operation(gang, actor=user) as op:
        fighter = op.hire(profile, "Kara", paid=100)
        xp = Counter.objects.create(name=f"XP {uuid4()}")
        table = RankTable.objects.create(name="Ranks", counter=xp)
        for threshold in (61, 64, 67):
            RankThreshold.objects.create(rank_table=table, threshold=threshold)
        action = Action.objects.create(
            name="Advancement",
            timing=Action.Timing.POST_CYCLE,
            rank_allowance_rule=RankAllowanceRule.objects.create(counter=xp),
        )
        op.assign(action, miniature=fighter)
        op.assign(table, miniature=fighter)
        held = op.assign(xp, miniature=fighter)
        value = op.open_counter(held, 61)
        op.event(
            held,
            LedgerEvent.Kind.COUNTER_CHECKPOINTED,
            counter_before=61,
            counter_delta=6,
            counter_after=67,
        )
        value.value = 67
        value.save(update_fields=["value"])
    return gang, fighter, action, held


def test_initialisation_grants_only_thresholds_above_the_start(legacy_fighter):
    gang, fighter, action, _ = legacy_fighter
    plan = find()
    assert plan.problems == ()
    assert plan.gangs == ((gang.pk,),)

    apply_one(gang.pk)
    assert set(
        ActionAllowance.objects.filter(fighter=fighter, action=action).values_list(
            "threshold", flat=True
        )
    ) == {64, 67}

    apply_one(gang.pk)
    assert ActionAllowance.objects.filter(fighter=fighter, action=action).count() == 2


def test_missing_baseline_is_reported_and_skipped(legacy_fighter):
    gang, fighter, action, held = legacy_fighter
    held.ledger_events.all().delete()
    LedgerEvent.objects.create(
        gang=gang,
        assignment=held,
        kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED,
        counter_before=0,
        counter_delta=67,
        counter_after=67,
    )
    plan = find()
    assert len(plan.missing_baselines) == 1
    assert "no original opening" in plan.missing_baselines[0]

    apply_one(gang.pk)
    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()


def test_preview_builds_effective_action_access_once_per_fighter(
    legacy_fighter, monkeypatch
):
    gang, fighter, _, _ = legacy_fighter
    with operation(gang) as op:
        for number in range(5):
            counter = Counter.objects.create(name=f"Unrelated {number}")
            held = op.assign(counter, miniature=fighter)
            op.open_counter(held, number)
    calls = 0
    real = action_initialisation.actions_for

    def watched(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(action_initialisation, "actions_for", watched)
    find()
    assert calls == 1


def test_task_delivery_records_progress_and_is_idempotent(legacy_fighter):
    gang, fighter, action, _ = legacy_fighter
    record = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"preview": find().preview(), "attempts": 0},
    )
    maintenance.initialise_action_allowances.call(backfill_id=str(record.pk))
    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    assert record.summary["done"] == 1
    assert ActionAllowance.objects.filter(fighter=fighter, action=action).count() == 2

    maintenance.initialise_action_allowances.call(backfill_id=str(record.pk))
    assert ActionAllowance.objects.filter(fighter=fighter, action=action).count() == 2


def test_admin_preview_is_read_only_and_post_enqueues(
    client, admin_user, legacy_fighter
):
    _, fighter, action, _ = legacy_fighter
    client.force_login(admin_user)
    address = reverse("admin:maintenance_n26_initialise_action_allowances")
    page = client.get(address)
    assert page.status_code == 200
    assert "1 gang(s) contain legacy fighter counters" in page.content.decode()
    assert not Backfill.objects.exists()

    response = client.post(address)
    assert response.status_code == 302
    run = Backfill.objects.get(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES
    )
    assert run.status == Backfill.Status.DONE
    assert ActionAllowance.objects.filter(fighter=fighter, action=action).count() == 2

    replacement = RankTable.objects.create(
        name="Replacement ranks", counter=action.rank_allowance_rule.counter
    )
    RankThreshold.objects.create(rank_table=replacement, threshold=66)
    second = client.post(address)
    assert second.status_code == 302
    assert (
        Backfill.objects.filter(
            operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES
        ).count()
        == 1
    )
    assert not ActionAllowance.objects.filter(
        fighter=fighter, action=action, threshold=66
    ).exists()


def test_a_new_task_record_refuses_after_a_successful_run(legacy_fighter):
    gang, fighter, action, _ = legacy_fighter
    first = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"preview": find().preview(), "attempts": 0},
    )
    maintenance.initialise_action_allowances.call(backfill_id=str(first.pk))
    second = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 0},
    )
    maintenance.initialise_action_allowances.call(backfill_id=str(second.pk))
    second.refresh_from_db()
    assert second.status == Backfill.Status.FAILED
    assert "already initialised" in second.error
    assert ActionAllowance.objects.filter(fighter=fighter, action=action).count() == 2


def test_completed_run_is_checked_after_taking_the_single_flight_lock(
    legacy_fighter, monkeypatch
):
    first = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.DONE,
    )
    second = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 0},
    )
    entered = False

    @contextmanager
    def observed_lock(_key):
        nonlocal entered
        entered = True
        yield True

    monkeypatch.setattr(maintenance, "_single_flight", observed_lock)
    maintenance.initialise_action_allowances.call(backfill_id=str(second.pk))

    second.refresh_from_db()
    assert entered
    assert second.status == Backfill.Status.FAILED
    assert "already initialised" in second.error
    assert first.status == Backfill.Status.DONE


def test_a_prior_attempt_competing_record_retries_after_the_lock_holder_finishes(
    monkeypatch,
):
    running = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
    )
    queued = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 1},
    )
    lock_is_free = False
    enqueued = []

    @contextmanager
    def lock(_key):
        yield lock_is_free

    monkeypatch.setattr(maintenance, "_single_flight", lock)
    monkeypatch.setattr(
        type(maintenance.initialise_action_allowances),
        "enqueue",
        lambda self, **kwargs: enqueued.append(kwargs),
    )
    maintenance.initialise_action_allowances.call(backfill_id=str(queued.pk))

    queued.refresh_from_db()
    assert queued.status == Backfill.Status.RUNNING
    assert enqueued == [{"backfill_id": str(queued.pk)}]

    running.status = Backfill.Status.DONE
    running.save(update_fields=["status", "modified"])
    lock_is_free = True
    maintenance.initialise_action_allowances.call(**enqueued.pop())

    queued.refresh_from_db()
    assert queued.status == Backfill.Status.FAILED
    assert "already initialised" in queued.error


def test_a_duplicate_delivery_does_not_end_the_active_record(monkeypatch):
    active = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 1},
    )
    lock_is_free = False
    enqueued = []

    @contextmanager
    def lock(_key):
        yield lock_is_free

    monkeypatch.setattr(maintenance, "_single_flight", lock)
    monkeypatch.setattr(
        type(maintenance.initialise_action_allowances),
        "enqueue",
        lambda self, **kwargs: enqueued.append(kwargs),
    )
    maintenance.initialise_action_allowances.call(backfill_id=str(active.pk))

    active.refresh_from_db()
    assert active.status == Backfill.Status.RUNNING
    assert enqueued == [{"backfill_id": str(active.pk)}]

    active.status = Backfill.Status.DONE
    active.save(update_fields=["status", "modified"])
    lock_is_free = True
    maintenance.initialise_action_allowances.call(**enqueued.pop())

    active.refresh_from_db()
    assert active.status == Backfill.Status.DONE


def test_application_reuses_the_prepared_card_access(legacy_fighter, monkeypatch):
    gang, fighter, action, _ = legacy_fighter

    def rebuilt(*args, **kwargs):
        raise AssertionError("allowance grant rebuilt prepared fighter access")

    monkeypatch.setattr(allowances, "actions_for", rebuilt)
    monkeypatch.setattr(allowances, "rank_table_for", rebuilt)

    apply_one(gang.pk)

    assert ActionAllowance.objects.filter(fighter=fighter, action=action).count() == 2


@pytest.mark.parametrize("change", ["archive", "delete"])
def test_a_planned_gang_that_disappears_is_skipped(legacy_fighter, change):
    gang, fighter, action, _ = legacy_fighter
    assert find().gangs == ((gang.pk,),)
    gang_id = gang.pk
    if change == "archive":
        gang.archived = True
        gang.save(update_fields=["archived", "modified"])
    else:
        gang.delete()

    report = apply_one(gang_id)

    assert "skipped" in report
    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()
