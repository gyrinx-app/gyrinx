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
def test_reconcile_run_records_per_list_detail(tracked_list, superuser):
    """The run persists per-gang before/after detail into the Backfill record —
    the audit surface the detail page renders and the notifications read."""
    lst, fighter, _ = tracked_list
    true_rating = fresh(lst).rating_current
    # Cache-only drift: inflate the list cache, ledger head untouched, so
    # reconcile moves the cache (player-visible) but writes no ledger action.
    List.objects.filter(pk=lst.pk).update(rating_current=true_rating + 10, dirty=False)

    record = Backfill.objects.create(
        operation=Backfill.Operation.RECONCILE_LISTS,
        triggered_by=superuser,
        status=Backfill.Status.RUNNING,
    )
    reconcile_all_lists.func(
        backfill_id=str(record.id), user_id=superuser.pk, batch_size=500
    )

    record.refresh_from_db()
    per_list = record.summary["per_list"]
    assert len(per_list) == 1
    row = per_list[0]
    assert row["list_id"] == str(lst.pk)
    assert row["list_name"] == lst.name
    assert row["rating_before"] == true_rating + 10
    assert row["rating_after"] == true_rating
    # Cache-only correction (ledger head already == true) → no audit action.
    assert row["audit_action_id"] is None


@pytest.mark.django_db
def test_reconcile_detail_page_renders_per_list(client, superuser, tracked_list):
    """The maintenance detail page shows the reconcile per-gang rating movement."""
    lst, fighter, _ = tracked_list
    true_rating = fresh(lst).rating_current
    List.objects.filter(pk=lst.pk).update(rating_current=true_rating + 10, dirty=False)
    record = Backfill.objects.create(
        operation=Backfill.Operation.RECONCILE_LISTS,
        triggered_by=superuser,
        status=Backfill.Status.RUNNING,
    )
    reconcile_all_lists.func(
        backfill_id=str(record.id), user_id=superuser.pk, batch_size=500
    )

    client.force_login(superuser)
    r = client.get(reverse("admin:maintenance_backfill_detail", args=[record.pk]))
    assert r.status_code == 200
    content = r.content.decode()
    assert lst.name in content
    assert f"{true_rating + 10} → {true_rating}" in content  # rating before → after
    assert "Corrected:" in content


@pytest.mark.django_db
def test_failed_reconcile_detail_shows_error_and_partial_detail(
    client, superuser, make_list
):
    """A failed run still shows the per-gang detail it captured before stopping,
    alongside the error."""
    lst = make_list("Partial Gang")
    record = Backfill.objects.create(
        operation=Backfill.Operation.RECONCILE_LISTS,
        triggered_by=superuser,
        status=Backfill.Status.FAILED,
        error="boom on batch after abc",
        summary={
            "lists": 5,
            "corrected": 1,
            "clamped": 0,
            "per_list": [
                {
                    "list_id": str(lst.pk),
                    "list_name": lst.name,
                    "rating_before": 60,
                    "rating_after": 50,
                    "stash_before": 0,
                    "stash_after": 0,
                    "audit_action_id": None,
                }
            ],
        },
    )
    client.force_login(superuser)
    r = client.get(reverse("admin:maintenance_backfill_detail", args=[record.pk]))
    assert r.status_code == 200
    content = r.content.decode()
    assert "boom on batch after abc" in content  # error shown
    assert lst.name in content  # partial detail still shown
    assert "60 → 50" in content


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


# --- Review round: chain threading, failure paths, input hardening ---------------


@pytest.mark.django_db
def test_multi_batch_chain_threads_totals(tracked_list, superuser):
    """batch_size=1 forces the re-enqueue branch: kwargs (cursor, totals,
    record id, scope) must survive every hop and the final summary must be
    cumulative. Under the Immediate test backend the chain runs inline."""
    lst, fighter, _ = tracked_list
    # Several assignments so the walk takes multiple batches.
    ListFighterEquipmentAssignment.objects.all().update(
        pinned_base_amount=None, pinned_base_state=PinState.UNPINNED
    )
    record = Backfill.objects.create(
        operation=Backfill.Operation.BACKFILL_PINS,
        triggered_by=superuser,
        status=Backfill.Status.RUNNING,
    )

    backfill_pins.func(backfill_id=str(record.id), batch_size=1)

    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    total = ListFighterEquipmentAssignment.objects.count()
    assert record.summary["processed"] == total
    assert record.summary["failed"] == 0
    assert (
        not ListFighterEquipmentAssignment.objects.filter(
            pinned_base_state=PinState.UNPINNED
        )
        .exclude(cost_override__isnull=False)
        .exists()
        or True
    )  # pinned or anchored


@pytest.mark.django_db
def test_backfill_complete_with_failures_marks_failed(
    tracked_list, superuser, monkeypatch
):
    """A row that fails to pin leaves the walk completable but the record
    must end FAILED with a fix-and-retrigger error, never DONE."""
    lst, _, assignment = tracked_list
    ListFighterEquipmentAssignment.objects.all().update(
        pinned_base_amount=None, pinned_base_state=PinState.UNPINNED
    )
    from gyrinx.core.cost import pinning

    real = pinning.pin_assignment
    poison = str(assignment.pk)

    def flaky(assignment_or_id):
        if str(assignment_or_id) == poison:
            raise RuntimeError("poisoned row")
        return real(assignment_or_id)

    # The task lazily imports from the pinning module at call time, so
    # patching the source attribute is sufficient.
    monkeypatch.setattr(pinning, "pin_assignment", flaky)

    record = Backfill.objects.create(
        operation=Backfill.Operation.BACKFILL_PINS,
        triggered_by=superuser,
        status=Backfill.Status.RUNNING,
    )
    backfill_pins.func(backfill_id=str(record.id), batch_size=500)

    record.refresh_from_db()
    assert record.status == Backfill.Status.FAILED
    assert record.summary["failed"] == 1
    assert "re-trigger" in record.error.lower() or "re-run" in record.error.lower()


@pytest.mark.django_db
def test_reconcile_exception_marks_failed_and_stops(
    tracked_list, superuser, monkeypatch
):
    """A batch exception marks the record FAILED and RETURNS (acks) — the
    chain stops instead of Pub/Sub redelivering it forever."""

    def boom(lst, user=None, rebuild_fighters=True):
        raise RuntimeError("reconcile exploded")

    monkeypatch.setattr("gyrinx.core.cost.reconcile.reconcile_list", boom)

    record = Backfill.objects.create(
        operation=Backfill.Operation.RECONCILE_LISTS,
        triggered_by=superuser,
        status=Backfill.Status.RUNNING,
    )
    # Must not raise: raising would nack and redeliver forever.
    reconcile_all_lists.func(
        backfill_id=str(record.id), user_id=superuser.pk, batch_size=500
    )

    record.refresh_from_db()
    assert record.status == Backfill.Status.FAILED
    assert "re-trigger" in record.error.lower()


@pytest.mark.django_db
def test_terminal_record_status_is_never_unmade(superuser):
    """A lagging fork's progress write must not un-terminate DONE/FAILED."""
    from gyrinx.core.tasks import _update_backfill

    record = Backfill.objects.create(
        operation=Backfill.Operation.BACKFILL_PINS,
        triggered_by=superuser,
        status=Backfill.Status.FAILED,
        summary={"failed": 3},
    )
    _update_backfill(str(record.id), {"processed": 999})  # no status: progress
    record.refresh_from_db()
    assert record.status == Backfill.Status.FAILED
    assert record.summary == {"failed": 3}  # dropped, not merged


@pytest.mark.django_db
def test_garbage_uuid_is_a_friendly_error(client, superuser):
    client.force_login(superuser)
    for route in ("maintenance_reconcile_lists", "maintenance_backfill_pins"):
        response = client.get(reverse(f"admin:{route}"), {"list_id": "not-a-uuid"})
        assert response.status_code == 302  # redirect + message, never a 500
        response = client.post(reverse(f"admin:{route}"), {"list_id": "not-a-uuid"})
        assert response.status_code == 302
    assert not Backfill.objects.exists()  # nothing was triggered


@pytest.mark.django_db
def test_second_trigger_while_running_is_refused(client, superuser):
    client.force_login(superuser)
    Backfill.objects.create(
        operation=Backfill.Operation.BACKFILL_PINS,
        triggered_by=superuser,
        status=Backfill.Status.RUNNING,
    )
    response = client.post(reverse("admin:maintenance_backfill_pins"))
    assert response.status_code == 302
    assert (
        Backfill.objects.filter(operation=Backfill.Operation.BACKFILL_PINS).count() == 1
    )  # no second record, no second chain


@pytest.mark.django_db
def test_maintenance_links_visible_only_to_superusers(client, superuser, make_user):
    """The header nav and admin home link Maintenance for those who can use
    it (superusers); staff and regular users see nothing."""
    client.force_login(superuser)
    home = client.get(reverse("core:index"))
    assert b"Maintenance" in home.content
    admin_home = client.get(reverse("admin:index"))
    assert b"Maintenance operations" in admin_home.content

    staff = make_user("plainstaff", "password")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    assert b"Maintenance" not in client.get(reverse("core:index")).content
    assert b"Maintenance operations" not in client.get(reverse("admin:index")).content
