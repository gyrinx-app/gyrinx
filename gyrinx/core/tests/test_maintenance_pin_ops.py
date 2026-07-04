"""Phase 8b (#1826): the admin maintenance triggers for reconcile + backfill.

Production runs on Cloud Run — there is no shell — so the two Phase 8
operations are triggered from /admin/maintenance/, run on the task runner in
self-re-enqueueing batches, and report progress into a Backfill audit record
(status RUNNING → DONE/FAILED, summary updated batch by batch).
"""

import pytest
from django.urls import reverse

from gyrinx.core.models import Backfill
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    PinState,
)
from gyrinx.core.tasks import backfill_pins, reconcile_all_lists
from gyrinx.core.tests.test_balance_sheet import buy_equipment, fresh, hire_fighter
from gyrinx.tasks.registry import get_task


@pytest.fixture
def tracked_list(user, make_list, content_fighter, make_equipment, campaign):
    lst = make_list("Maint Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Stake",
        credits_delta=1000,
        update_credits=True,
    )
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    assignment = buy_equipment(user, lst, fighter, make_equipment("Lasgun", cost=15))
    return lst, fighter, assignment


@pytest.fixture
def superuser(make_user):
    u = make_user("maintops", "password")
    u.is_staff = True
    u.is_superuser = True
    u.save()
    return u


# --- Tasks report into the audit record ----------------------------------------


@pytest.mark.django_db
def test_reconcile_task_reports_progress_and_attribution(tracked_list, superuser, user):
    lst, fighter, _ = tracked_list
    # Hidden drift so there is something to correct and attribute.
    true_rating = fresh(lst).rating_current
    ListFighter.objects.filter(pk=fighter.pk).update(
        rating_current=fighter.rating_current + 10, dirty=False
    )
    List.objects.filter(pk=lst.pk).update(rating_current=true_rating + 10, dirty=False)
    # Genuine ledger movement too: strip the pin and reprice the equipment.
    ListFighterEquipmentAssignment.objects.filter(list_fighter__list=lst).update(
        pinned_base_amount=None, pinned_base_state=PinState.UNPINNED
    )

    record = Backfill.objects.create(
        operation=Backfill.Operation.RECONCILE_LISTS,
        triggered_by=superuser,
        status=Backfill.Status.RUNNING,
    )
    reconcile_all_lists.func(
        backfill_id=str(record.id), user_id=superuser.pk, batch_size=500
    )

    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    assert record.summary["lists"] >= 1
    assert record.summary["corrected"] >= 1
    assert fresh(lst).rating_current == true_rating
    # RECONCILE actions attribute to the triggering operator, not the owner.
    action = ListAction.objects.filter(
        list=lst, action_type=ListActionType.RECONCILE
    ).first()
    if action:
        assert action.user == superuser


@pytest.mark.django_db
def test_backfill_task_reports_progress(tracked_list, superuser):
    lst, _, assignment = tracked_list
    ListFighterEquipmentAssignment.objects.all().update(
        pinned_base_amount=None, pinned_base_state=PinState.UNPINNED
    )
    record = Backfill.objects.create(
        operation=Backfill.Operation.BACKFILL_PINS,
        triggered_by=superuser,
        status=Backfill.Status.RUNNING,
    )

    backfill_pins.func(backfill_id=str(record.id), batch_size=500)

    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    assert record.summary["rows_pinned"] >= 1
    assert record.summary["failed"] == 0
    row = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
    assert row.pinned_base_state == PinState.CATALOG


# --- The admin trigger pages ------------------------------------------------------


@pytest.mark.django_db
def test_maintenance_pages_render_and_trigger(
    client, superuser, tracked_list, django_capture_on_commit_callbacks
):
    client.force_login(superuser)

    for route in ("maintenance_reconcile_lists", "maintenance_backfill_pins"):
        response = client.get(reverse(f"admin:{route}"))
        assert response.status_code == 200

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("admin:maintenance_backfill_pins"))
    assert response.status_code == 302
    record = Backfill.objects.filter(operation=Backfill.Operation.BACKFILL_PINS).latest(
        "created"
    )
    assert record.triggered_by == superuser
    # Under the dev/test Immediate backend the enqueued chain runs inline,
    # so the record has already progressed past RUNNING.
    assert record.status in (Backfill.Status.RUNNING, Backfill.Status.DONE)


@pytest.mark.django_db
def test_maintenance_pages_are_superuser_only(client, make_user):
    staff = make_user("staffonly", "password")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    for route in ("maintenance_reconcile_lists", "maintenance_backfill_pins"):
        assert client.get(reverse(f"admin:{route}")).status_code == 403
        assert client.post(reverse(f"admin:{route}")).status_code == 403


# --- The #1947 lesson, enforced by hand until the system check lands ------------


def test_maintenance_tasks_are_registered():
    assert get_task("backfill_pins") is not None
    assert get_task("reconcile_all_lists") is not None


# --- Incremental rollout: per-list scoping ---------------------------------------


@pytest.mark.django_db
def test_scoped_backfill_touches_only_the_target_list(
    tracked_list, superuser, user, make_list, content_fighter, make_equipment, campaign
):
    """Scoping a run to one list receipts that list's gear and leaves every
    other gang's rows untouched — the incremental-rollout mechanism."""
    lst, _, assignment = tracked_list
    other = make_list("Other Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(other)
    other.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Stake",
        credits_delta=500,
        update_credits=True,
    )
    other_fighter = hire_fighter(user, other, content_fighter, name="Eve")
    other_assignment = buy_equipment(
        user, other, other_fighter, make_equipment("Other Gun", cost=20)
    )
    ListFighterEquipmentAssignment.objects.all().update(
        pinned_base_amount=None, pinned_base_state=PinState.UNPINNED
    )

    record = Backfill.objects.create(
        operation=Backfill.Operation.BACKFILL_PINS,
        triggered_by=superuser,
        list_id_scope=lst.pk,
        status=Backfill.Status.RUNNING,
    )
    backfill_pins.func(backfill_id=str(record.id), list_id=str(lst.pk), batch_size=500)

    assert (
        ListFighterEquipmentAssignment.objects.get(pk=assignment.pk).pinned_base_state
        == PinState.CATALOG
    )
    assert (
        ListFighterEquipmentAssignment.objects.get(
            pk=other_assignment.pk
        ).pinned_base_state
        == PinState.UNPINNED
    )
    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE


@pytest.mark.django_db
def test_scoped_reconcile_touches_only_the_target_list(
    tracked_list, superuser, user, make_list, content_fighter, campaign
):
    lst, fighter, _ = tracked_list
    other = make_list("Other Gang R", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(other)
    other.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Stake",
        credits_delta=500,
        update_credits=True,
    )
    other_fighter = hire_fighter(user, fresh(other), content_fighter, name="Eve")
    # Drift on BOTH lists; only the scoped one gets corrected.
    true_fighter = fresh(fighter).rating_current
    true_other = fresh(other_fighter).rating_current
    for target, f in ((lst, fighter), (other, other_fighter)):
        ListFighter.objects.filter(pk=f.pk).update(
            rating_current=fresh(f).rating_current + 10, dirty=False
        )
        List.objects.filter(pk=target.pk).update(
            rating_current=fresh(target).rating_current + 10, dirty=False
        )

    record = Backfill.objects.create(
        operation=Backfill.Operation.RECONCILE_LISTS,
        triggered_by=superuser,
        list_id_scope=lst.pk,
        status=Backfill.Status.RUNNING,
    )
    reconcile_all_lists.func(
        backfill_id=str(record.id),
        user_id=superuser.pk,
        list_id=str(lst.pk),
        batch_size=500,
    )

    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    assert record.summary["lists"] == 1
    assert fresh(fighter).rating_current == true_fighter  # corrected
    assert fresh(other_fighter).rating_current == true_other + 10  # untouched
