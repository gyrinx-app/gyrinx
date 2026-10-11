from contextlib import contextmanager
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from n26 import maintenance
from n26.core import action_initialisation, allowances
from n26.core.action_initialisation import INACTIVE_REASON, apply_one, find
from n26.core.models import ActionAllowance, CounterTracking, Gang, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.library.models import (
    Action,
    Counter,
    RankAllowanceRule,
    RankTable,
    RankThreshold,
)

pytestmark = pytest.mark.django_db


def completed_preview():
    record = Backfill.objects.create(
        operation=maintenance.Operation.PREVIEW_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 0},
    )
    maintenance.preview_action_allowances.call(backfill_id=str(record.pk))
    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    return record


@pytest.fixture
def legacy_fighter(user, gang_type, make_profile, make_statline, counter_tracking):
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
            LedgerEvent.Kind.TALLIED,
            counter_before=61,
            counter_delta=6,
            counter_after=67,
        )
        value.value = 67
        value.save(update_fields=["value"])
    return gang, fighter, action, held


@pytest.mark.core
def test_inactive_counter_history_refuses_the_plan(legacy_fighter):
    CounterTracking.objects.all().delete()

    plan = find()

    assert plan.gangs == ()
    assert plan.missing_baselines == ()
    assert plan.problems == (INACTIVE_REASON,)


@pytest.mark.core
def test_application_rechecks_counter_history_under_the_gang_operation(
    legacy_fighter,
):
    gang, fighter, action, _ = legacy_fighter
    CounterTracking.objects.all().delete()

    with pytest.raises(Refusal, match="Activate counter history"):
        apply_one(gang.pk)

    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()


@pytest.mark.core
def test_inactive_counter_history_fails_the_task_instead_of_recording_done(
    legacy_fighter,
):
    CounterTracking.objects.all().delete()
    record = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 0},
    )

    maintenance.initialise_action_allowances.call(backfill_id=str(record.pk))

    record.refresh_from_db()
    assert record.status == Backfill.Status.FAILED
    assert "Activate counter history" in record.error


def test_inactive_counter_history_is_explained_on_the_maintenance_page(
    client, admin_user, legacy_fighter
):
    CounterTracking.objects.all().delete()
    client.force_login(admin_user)
    address = reverse("admin:maintenance_n26_initialise_action_allowances")

    page = client.get(address)

    assert page.status_code == 200
    assert b"Activate counter history before initialising" in page.content
    assert b"Initialise earned allowances" not in page.content

    response = client.post(address, follow=True)
    assert response.status_code == 200
    assert b"Activate counter history before initialising" in response.content
    assert not Backfill.objects.filter(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES
    ).exists()


@pytest.mark.core
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


@pytest.mark.core
def test_missing_baseline_is_reported_and_skipped(legacy_fighter):
    gang, fighter, action, held = legacy_fighter
    held.ledger_events.all().delete()
    LedgerEvent.objects.create(
        gang=gang,
        assignment=held,
        kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED,
        counter_before=67,
        counter_delta=0,
        counter_after=67,
    )
    plan = find()
    assert len(plan.missing_baselines) == 1
    assert "no original opening" in plan.missing_baselines[0]

    apply_one(gang.pk)
    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()


def test_a_rank_table_conflict_does_not_abort_other_counters(legacy_fighter):
    gang, fighter, conflicted_action, held = legacy_fighter
    conflict = RankTable.objects.create(name="Conflicting ranks", counter=held.counter)
    RankThreshold.objects.create(rank_table=conflict, threshold=64)
    second_counter = Counter.objects.create(name=f"Second XP {uuid4()}")
    second_table = RankTable.objects.create(name="Second ranks", counter=second_counter)
    for threshold in (61, 64, 67):
        RankThreshold.objects.create(rank_table=second_table, threshold=threshold)
    second_action = Action.objects.create(
        name="Second advancement",
        timing=Action.Timing.POST_CYCLE,
        rank_allowance_rule=RankAllowanceRule.objects.create(counter=second_counter),
    )
    with operation(gang) as op:
        op.assign(conflict, miniature=fighter)
        op.assign(second_action, miniature=fighter)
        op.assign(second_table, miniature=fighter)
        second_held = op.assign(second_counter, miniature=fighter)
        value = op.open_counter(second_held, 61)
        op.event(
            second_held,
            LedgerEvent.Kind.TALLIED,
            counter_before=61,
            counter_delta=6,
            counter_after=67,
        )
        value.value = 67
        value.save(update_fields=["value"])

    plan = find()
    assert plan.gangs == ((gang.pk,),)
    assert len(plan.problems) == 1

    summary = apply_one(gang.pk)

    assert "granted 2 earned use(s); skipped 1 counter(s)" in summary
    assert not ActionAllowance.objects.filter(
        fighter=fighter, action=conflicted_action
    ).exists()
    assert (
        ActionAllowance.objects.filter(fighter=fighter, action=second_action).count()
        == 2
    )


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


@pytest.mark.core
def test_task_delivery_records_progress_and_is_idempotent(legacy_fighter, monkeypatch):
    gang, fighter, action, _ = legacy_fighter
    record = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"preview_id": str(completed_preview().pk), "attempts": 0},
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Initialisation repeated the full preview scan")

    monkeypatch.setattr(action_initialisation, "find", forbidden)
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
    assert "Prepare preview" in page.content.decode()
    assert not Backfill.objects.exists()

    response = client.post(address, {"action": "preview"})
    assert response.status_code == 302
    preview = Backfill.objects.get(
        operation=maintenance.Operation.PREVIEW_ACTION_ALLOWANCES
    )
    assert preview.status == Backfill.Status.DONE
    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()
    page = client.get(address)
    assert "1 gang(s) contain legacy fighter counters" in page.content.decode()
    response = client.post(address, {"preview_id": str(preview.pk)})
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


def test_requests_do_not_scan_fighters_and_query_growth_is_flat(
    client, admin_user, legacy_fighter, monkeypatch, task_queue
):
    gang, fighter, action, _ = legacy_fighter
    client.force_login(admin_user)
    address = reverse("admin:maintenance_n26_initialise_action_allowances")

    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP request scanned fighter cards")

    monkeypatch.setattr(action_initialisation, "find", forbidden)
    monkeypatch.setattr(action_initialisation, "candidates", forbidden)
    client.get(address)
    with CaptureQueriesContext(connection) as small:
        assert client.get(address).status_code == 200
    Gang.objects.bulk_create(
        [
            Gang(name=f"Extra {number}", owner=gang.owner, gang_type=gang.gang_type)
            for number in range(100)
        ]
    )
    with CaptureQueriesContext(connection) as large:
        assert client.get(address).status_code == 200
    assert len(large) <= len(small)

    with task_queue.capture():
        assert client.post(address, {"action": "preview"}).status_code == 302
    preview = Backfill.objects.get(
        operation=maintenance.Operation.PREVIEW_ACTION_ALLOWANCES
    )
    assert preview.status == Backfill.Status.RUNNING
    assert client.get(address).status_code == 200
    assert client.post(address, {"preview_id": str(preview.pk)}).status_code == 302
    assert not Backfill.objects.filter(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES
    ).exists()
    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()


def test_preview_is_read_only_idempotent_and_reports_conflicts(legacy_fighter):
    gang, fighter, action, held = legacy_fighter
    held.ledger_events.all().delete()
    preview = completed_preview()
    plan = maintenance._allowance_preview_plan(preview)
    assert len(plan.missing_baselines) == 1
    report = preview.summary["report"]
    maintenance.preview_action_allowances.call(backfill_id=str(preview.pk))
    preview.refresh_from_db()
    assert preview.summary["report"] == report
    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()

    conflict = RankTable.objects.create(name="Conflicting ranks", counter=held.counter)
    with operation(gang) as op:
        op.assign(conflict, miniature=fighter)
    plan = maintenance._allowance_preview_plan(completed_preview())
    assert len(plan.problems) == 1


def test_a_conflicted_preview_blocks_the_admin_apply(
    client, admin_user, legacy_fighter
):
    gang, fighter, _, held = legacy_fighter
    conflict = RankTable.objects.create(name="Conflicting ranks", counter=held.counter)
    with operation(gang) as op:
        op.assign(conflict, miniature=fighter)
    preview = completed_preview()
    client.force_login(admin_user)
    address = reverse("admin:maintenance_n26_initialise_action_allowances")
    page = client.get(address)
    assert b"Problems to resolve" in page.content
    assert b"Initialise earned allowances" not in page.content
    assert client.post(address, {"preview_id": str(preview.pk)}).status_code == 302
    assert not Backfill.objects.filter(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES
    ).exists()
    assert not ActionAllowance.objects.exists()


def test_preview_detail_shows_progress_without_raw_scan_results(
    client, admin_user, legacy_fighter
):
    preview = completed_preview()
    client.force_login(admin_user)
    page = client.get(reverse("admin:maintenance_backfill_detail", args=[preview.pk]))
    assert page.status_code == 200
    assert b"1 of 1 gangs checked" in page.content
    assert b"Review allowance initialisation" in page.content
    assert b"missing_baselines" not in page.content


@pytest.mark.parametrize(
    "status",
    [Backfill.Status.RUNNING, Backfill.Status.FAILED, Backfill.Status.CANCELLED],
)
def test_partial_previews_cannot_authorise_initialisation(legacy_fighter, status):
    preview = completed_preview()
    preview.status = status
    preview.save(update_fields=["status", "modified"])
    record = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        summary={"preview_id": str(preview.pk), "attempts": 0},
        status=Backfill.Status.RUNNING,
    )
    maintenance.initialise_action_allowances.call(backfill_id=str(record.pk))
    record.refresh_from_db()
    assert record.status == Backfill.Status.FAILED
    assert "completed allowance preview" in record.error
    assert not ActionAllowance.objects.exists()


def test_completed_empty_preview_is_reviewable(counter_tracking):
    plan = maintenance._allowance_preview_plan(completed_preview())
    assert plan.nothing_here
    assert not plan.problems


def test_preview_resumes_from_its_frozen_gang_list(
    legacy_fighter, monkeypatch, task_queue
):
    from datetime import timedelta

    from n26.core.action_initialisation import InitialisationPlan

    gang, fighter, action, _ = legacy_fighter
    extra = Gang.objects.create(
        name="Extra", owner=gang.owner, gang_type=gang.gang_type
    )
    calls = []
    real_find = action_initialisation.find

    def watched(gang):
        calls.append(gang.pk)
        return real_find(gang)

    monkeypatch.setattr(action_initialisation, "find", watched)
    monkeypatch.setattr(
        action_initialisation,
        "candidates",
        lambda: InitialisationPlan(((gang.pk,), (extra.pk,)), (), ()),
    )
    real_run = maintenance.run_per_gang

    def short_delivery(*args, **kwargs):
        return real_run(*args, **kwargs, batch_size=1, budget=timedelta(seconds=-1))

    monkeypatch.setattr(maintenance, "run_per_gang", short_delivery)
    preview = Backfill.objects.create(
        operation=maintenance.Operation.PREVIEW_ACTION_ALLOWANCES,
        summary={"attempts": 0},
        status=Backfill.Status.RUNNING,
    )
    with task_queue.capture():
        maintenance.preview_action_allowances.call(backfill_id=str(preview.pk))
    preview.refresh_from_db()
    assert preview.status == Backfill.Status.RUNNING
    assert preview.summary["done"] == 1

    def forbidden():
        raise AssertionError("Continuation rebuilt its frozen gang list")

    monkeypatch.setattr(action_initialisation, "candidates", forbidden)
    task_queue.deliver_all()
    preview.refresh_from_db()
    assert preview.status == Backfill.Status.DONE
    assert preview.summary["done"] == 2
    assert set(calls) == {gang.pk, extra.pk}
    assert len(calls) == 2
    assert maintenance._allowance_preview_plan(preview).gangs == ((str(gang.pk),),)
    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()


@pytest.mark.core
def test_a_new_task_record_refuses_after_a_successful_run(legacy_fighter):
    gang, fighter, action, _ = legacy_fighter
    first = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"preview_id": str(completed_preview().pk), "attempts": 0},
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


@pytest.mark.core
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


@pytest.mark.core
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

    @contextmanager
    def lock(_key):
        yield lock_is_free

    monkeypatch.setattr(maintenance, "_single_flight", lock)
    with pytest.raises(RuntimeError, match="already running"):
        maintenance.initialise_action_allowances.call(backfill_id=str(queued.pk))

    queued.refresh_from_db()
    assert queued.status == Backfill.Status.RUNNING

    running.status = Backfill.Status.DONE
    running.save(update_fields=["status", "modified"])
    lock_is_free = True
    maintenance.initialise_action_allowances.call(backfill_id=str(queued.pk))

    queued.refresh_from_db()
    assert queued.status == Backfill.Status.FAILED
    assert "already initialised" in queued.error


@pytest.mark.core
def test_a_duplicate_delivery_does_not_end_the_active_record(monkeypatch):
    active = Backfill.objects.create(
        operation=maintenance.Operation.INITIALISE_ACTION_ALLOWANCES,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 1},
    )
    lock_is_free = False

    @contextmanager
    def lock(_key):
        yield lock_is_free

    monkeypatch.setattr(maintenance, "_single_flight", lock)
    with pytest.raises(RuntimeError, match="already running"):
        maintenance.initialise_action_allowances.call(backfill_id=str(active.pk))

    active.refresh_from_db()
    assert active.status == Backfill.Status.RUNNING

    active.status = Backfill.Status.DONE
    active.save(update_fields=["status", "modified"])
    lock_is_free = True
    maintenance.initialise_action_allowances.call(backfill_id=str(active.pk))

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
