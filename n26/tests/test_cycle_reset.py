"""The one-off prelaunch reset retains facts and applies only its reviewed raw scope."""

from copy import deepcopy
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.urls import reverse
from django.utils import timezone

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import resolve_operation
from gyrinx.site.models import Availability, FeatureFlag, Notification, notify
from n26 import maintenance
from n26.core import cycle_reset as reset
from n26.core import cycles
from n26.core.models import (
    ActionRecord,
    Battle,
    BattleCommand,
    CampaignCycleCommand,
    CampaignCycleDelivery,
    CampaignCycleTransition,
    CampaignEvent,
    CampaignPlan,
    CampaignSchedule,
    CampaignScheduleTemplate,
    LedgerEvent,
)
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library import authoring as a
from n26.tests.test_cycle_attribution import record_battle, table  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def captured(table):  # noqa: F811
    battle = record_battle(table)
    BattleCommand.objects.create(
        campaign=table.campaign,
        actor=table.owner,
        battle=battle,
        request_key=uuid4(),
        kind="create",
        inputs={"cycle": str(battle.cycle_id)},
        revision=battle.revision,
    )
    action = a.create_action(
        "Prelaunch maintenance",
        "post_cycle",
        use_price=[{"resource": "credits", "payer": "gang", "amount": 10}],
    )
    with operation(table.gang, actor=table.owner) as op:
        op.assign(action, miniature=table.fighter)
    with operation(table.gang, actor=table.owner, cycle_context=table.context) as op:
        op.start_action(table.fighter, action, uuid4())
    state = cycles.load(table.campaign)
    cycles.start(
        table.campaign,
        actor=table.owner,
        expected_current=state.current_cycle_id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    transition = CampaignCycleTransition.objects.first()
    recipient = User.objects.create_user("reset-pending")
    CampaignCycleDelivery.objects.create(
        transition=transition,
        recipient=recipient,
        subject="Pending cycle notice",
    )
    recipient = User.objects.create_user("reset-delivered")
    notification = notify(recipient=recipient, subject="Delivered cycle notice")
    assert notification is not None
    CampaignCycleDelivery.objects.create(
        transition=transition,
        recipient=recipient,
        subject="Delivered cycle notice",
        notification_id=notification.pk,
        delivered_at=timezone.now(),
    )
    table.flag.availability = Availability.OFF
    table.flag.save()
    return table


def facts():
    result = {}
    for model in (
        Battle,
        ActionRecord,
        LedgerEvent,
        BattleCommand,
        CampaignEvent,
        Notification,
        CampaignScheduleTemplate,
    ):
        result[model.__name__] = [
            {key: value for key, value in row.items() if key != "cycle_id"}
            for row in model.objects.order_by("pk").values()
        ]
    return result


def apply(plan):
    return reset.apply(
        plan.recorded()["plan"],
        require_disabled=maintenance._require_prelaunch_cycle_flag_off,
    )


def test_reset_preserves_facts_and_receipts_and_clears_all_cycle_attribution(captured):
    plan = reset.find()
    before = facts()
    commands = list(CampaignCycleCommand.objects.order_by("pk").values())
    assert all(
        plan.counts[key]
        for key in ("battles", "actions", "ledger_events", "transitions")
    )
    assert plan.counts["deliveries_pending"] and plan.counts["deliveries_delivered"]
    assert any(str(captured.campaign.pk) in line for line in plan.preview())
    assert any(str(CampaignPlan.objects.first().pk) in line for line in plan.preview())
    apply(plan)
    assert facts() == before
    for model in (Battle, ActionRecord, LedgerEvent):
        assert not model.objects.exclude(cycle_id=None).exists()
    for key in reset.CATALOG:
        assert not reset.MODELS[key].objects.exists()
    after = list(CampaignCycleCommand.objects.order_by("pk").values())
    assert after == [{**row, "kind": reset.TOMBSTONE} for row in commands]
    assert_reconciled(captured.gang)


@pytest.mark.parametrize("orphaned", [False, True])
def test_invalid_stored_json_and_orphan_catalog_are_reset_without_loading_schedule(
    captured, monkeypatch, orphaned
):
    CampaignPlan.objects.update(steps={"not": "a valid plan"})
    CampaignSchedule.objects.update(date_settings={"legacy": "invalid"})
    if orphaned:
        CampaignSchedule.objects.all().delete()
    monkeypatch.setattr(
        cycles,
        "load",
        lambda *args: pytest.fail("Domain schedule loading is forbidden"),
    )
    plan = reset.find()
    assert plan.counts["cycles"] and plan.counts["plans"] and plan.counts["phases"]
    apply(plan)
    assert reset.find().nothing_here


@pytest.mark.parametrize(
    "changed", ["revision", "date_settings", "plan", "attribution"]
)
def test_changed_reviewed_scope_refuses_without_additional_writes(captured, changed):
    plan = reset.find()
    if changed == "revision":
        CampaignSchedule.objects.update(revision=123)
    elif changed == "date_settings":
        CampaignSchedule.objects.update(date_settings={"changed": True})
    elif changed == "plan":
        CampaignPlan.objects.update(steps=[])
    else:
        Battle.objects.update(cycle=None)
    before = reset.find().rows
    with pytest.raises(reset.ResetRefused, match="changed after the preview"):
        apply(plan)
    assert reset.find().rows == before


@pytest.mark.parametrize(
    "availability", [Availability.EVERYONE, Availability.ALLOWLIST]
)
def test_strict_flag_guard_refuses_every_non_off_state(captured, availability):
    plan = reset.find()
    FeatureFlag.objects.update(availability=availability)
    with pytest.raises(reset.ResetRefused, match="Turn campaign cycles off"):
        apply(plan)
    assert reset.find().rows == plan.rows


def test_absent_flag_is_allowed(captured):
    FeatureFlag.objects.all().delete()
    apply(reset.find())
    assert reset.find().nothing_here


def test_partial_failure_rolls_back_attribution_tombstones_and_deletions(
    captured, monkeypatch
):
    plan = reset.find()
    original_delete = QuerySet.delete

    def fail_at_plans(queryset):
        if queryset.model is CampaignPlan:
            raise RuntimeError("Injected failure after earlier writes")
        return original_delete(queryset)

    monkeypatch.setattr(QuerySet, "delete", fail_at_plans)
    with pytest.raises(RuntimeError, match="Injected failure"):
        apply(plan)
    assert reset.find().rows == plan.rows


def test_old_scope_is_idempotent_and_does_not_capture_a_new_schedule(captured):
    plan = reset.find()
    old_receipt = CampaignCycleCommand.objects.filter(kind="configure").get()
    template = CampaignScheduleTemplate.objects.first()
    apply(plan)
    captured.flag.availability = Availability.EVERYONE
    captured.flag.save()
    with pytest.raises(cycles.CycleKeyConflict):
        cycles.configure(
            captured.campaign,
            actor=captured.owner,
            template_id=template.pk,
            current_position=0,
            mode="fixed",
            request_key=old_receipt.request_key,
        )
    cycles.configure(
        captured.campaign,
        actor=captured.owner,
        template_id=template.pk,
        current_position=0,
        mode="fixed",
        request_key=uuid4(),
    )
    captured.flag.availability = Availability.OFF
    captured.flag.save()
    later = reset.find().rows
    assert "already reset" in apply(plan)[0]
    assert reset.find().rows == later


def address():
    return reverse("admin:maintenance_n26_reset_prelaunch_campaign_cycles")


def login(client):
    client.force_login(User.objects.create_superuser("reset-admin", password="test"))


def form_action(response):
    return BeautifulSoup(response.content, "html.parser").select_one("form.mt-form")[
        "action"
    ]


def test_console_posts_real_signed_form_and_redelivery_keeps_terminal_record(
    captured, client
):
    login(client)
    before = reset.find().rows
    page = client.get(address())
    assert page.status_code == 200
    assert reset.find().rows == before
    assert not Backfill.objects.exists()
    target = form_action(page)
    assert "scope=" in target
    assert client.post(target).status_code == 302
    run = Backfill.objects.get(
        operation=maintenance.Operation.RESET_PRELAUNCH_CAMPAIGN_CYCLES
    )
    assert run.status == Backfill.Status.DONE, run.error
    assert run.summary["plan"]["rows"] == before
    saved = deepcopy(run.summary)
    captured.flag.availability = Availability.EVERYONE
    captured.flag.save()
    cycles.configure(
        captured.campaign,
        actor=captured.owner,
        template_id=CampaignScheduleTemplate.objects.first().pk,
        current_position=0,
        mode="fixed",
        request_key=uuid4(),
    )
    captured.flag.availability = Availability.OFF
    captured.flag.save()
    later = reset.find().rows
    maintenance.reset_prelaunch_campaign_cycles.call(backfill_id=str(run.pk))
    run.refresh_from_db()
    assert run.summary == saved
    assert client.post(target).status_code == 302
    assert Backfill.objects.count() == 1
    assert reset.find().rows == later
    assert "Later schedules are kept" in client.get(address()).content.decode()


def test_preview_scope_drift_and_unsigned_post_cannot_queue(captured, client):
    login(client)
    target = form_action(client.get(address()))
    CampaignSchedule.objects.update(revision=123)
    assert client.post(target).status_code == 302
    assert client.post(address()).status_code == 302
    assert not Backfill.objects.exists()
    assert CampaignSchedule.objects.exists()


def test_worker_rechecks_flag_after_queue_and_rejects_foreign_backfill(captured):
    plan = reset.find()
    run = Backfill.objects.create(
        operation=maintenance.Operation.RESET_PRELAUNCH_CAMPAIGN_CYCLES,
        status=Backfill.Status.RUNNING,
        summary=plan.recorded(),
    )
    captured.flag.availability = Availability.EVERYONE
    captured.flag.save()
    maintenance.reset_prelaunch_campaign_cycles.call(backfill_id=str(run.pk))
    run.refresh_from_db()
    assert run.status == Backfill.Status.FAILED
    assert "Turn campaign cycles off" in run.error
    assert reset.find().rows == plan.rows
    other = Backfill.objects.create(
        operation="another_operation", status=Backfill.Status.RUNNING
    )
    maintenance.reset_prelaunch_campaign_cycles.call(backfill_id=str(other.pk))
    other.refresh_from_db()
    assert other.status == Backfill.Status.RUNNING and not other.summary


def test_operation_uses_exclusive_n26_task_and_separate_operation_lock():
    op = maintenance.Operation.RESET_PRELAUNCH_CAMPAIGN_CYCLES
    route = next(
        route
        for route in maintenance.task_routes
        if route.func == maintenance.reset_prelaunch_campaign_cycles
    )
    assert route.write_scope == "n26" and route.exclusive_write
    assert resolve_operation(op.value).write_scope is None
    assert len(maintenance.LOCK_KEYS.values()) == len(
        set(maintenance.LOCK_KEYS.values())
    )
