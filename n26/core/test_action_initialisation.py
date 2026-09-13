from uuid import uuid4

import pytest
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from n26 import maintenance
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
