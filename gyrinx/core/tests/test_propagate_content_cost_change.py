"""Tests for the async content-cost-change propagation task and its enqueue."""

from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import List, ListFighterEquipmentAssignment
from gyrinx.core.tasks import propagate_content_cost_change


@pytest.fixture
def cost_equipment(make_equipment):
    """Equipment with a known cost, in a real category."""
    return make_equipment("Boltgun", cost="100", category="Weapons & Ammo")


def _clean_list_with_equipment(make_list, make_list_fighter, cost_equipment):
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=cost_equipment,
    )
    lst.facts_from_db(update=True)
    lst.refresh_from_db()
    return lst


@pytest.mark.django_db
def test_task_recomputes_facts_and_creates_action(
    make_list, make_list_fighter, cost_equipment
):
    lst = _clean_list_with_equipment(make_list, make_list_fighter, cost_equipment)
    before = ListAction.objects.filter(list=lst).count()

    # Change cost directly (bypassing the signal) and mark affected rows dirty
    # exactly as the pre_save handler would, then run the task by hand.
    ContentEquipment = cost_equipment.__class__
    ContentEquipment.objects.filter(pk=cost_equipment.pk).update(cost="150")
    cost_equipment.refresh_from_db()
    cost_equipment.set_dirty()

    ct = ContentType.objects.get_for_model(ContentEquipment)
    propagate_content_cost_change.enqueue(
        content_type_id=ct.id, object_id=str(cost_equipment.pk)
    )

    after = ListAction.objects.filter(list=lst).count()
    assert after == before + 1
    action = ListAction.objects.filter(list=lst).order_by("-created").first()
    assert action.action_type == ListActionType.CONTENT_COST_CHANGE


@pytest.mark.django_db
def test_task_idempotent_on_second_run(make_list, make_list_fighter, cost_equipment):
    lst = _clean_list_with_equipment(make_list, make_list_fighter, cost_equipment)

    ContentEquipment = cost_equipment.__class__
    ContentEquipment.objects.filter(pk=cost_equipment.pk).update(cost="150")
    cost_equipment.refresh_from_db()
    cost_equipment.set_dirty()
    ct = ContentType.objects.get_for_model(ContentEquipment)

    propagate_content_cost_change.enqueue(
        content_type_id=ct.id, object_id=str(cost_equipment.pk)
    )
    after_first = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()

    # Second run: facts already up to date -> zero delta -> no new action.
    propagate_content_cost_change.enqueue(
        content_type_id=ct.id, object_id=str(cost_equipment.pk)
    )
    after_second = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()
    assert after_second == after_first


@pytest.mark.django_db
def test_task_missing_instance_is_noop(cost_equipment):
    ct = ContentType.objects.get_for_model(cost_equipment.__class__)
    # Stale object id -> task returns cleanly, raising nothing.
    propagate_content_cost_change.enqueue(
        content_type_id=ct.id,
        object_id="00000000-0000-0000-0000-000000000000",
    )


@pytest.mark.django_db
def test_signal_enqueues_on_commit_only(
    make_list,
    make_list_fighter,
    cost_equipment,
    django_capture_on_commit_callbacks,
):
    """The cost-change post_save defers enqueue to transaction.on_commit."""
    _clean_list_with_equipment(make_list, make_list_fighter, cost_equipment)

    with patch("gyrinx.core.tasks.propagate_content_cost_change") as mock_task:
        # Do not execute the callbacks: enqueue must not have happened yet.
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            cost_equipment.cost = "150"
            cost_equipment.save()
            mock_task.enqueue.assert_not_called()

        # Firing the captured callbacks enqueues exactly once.
        assert len(callbacks) >= 1
        for cb in callbacks:
            cb()
        mock_task.enqueue.assert_called_once()


@pytest.mark.django_db
def test_signal_does_not_enqueue_when_cost_unchanged(
    cost_equipment, django_capture_on_commit_callbacks
):
    with patch("gyrinx.core.tasks.propagate_content_cost_change") as mock_task:
        # Saving with the same cost must not enqueue.
        with django_capture_on_commit_callbacks(execute=True):
            cost_equipment.save()
        mock_task.enqueue.assert_not_called()


@pytest.mark.django_db
def test_view_before_task_still_records_action(
    make_list,
    make_list_fighter,
    cost_equipment,
    django_capture_on_commit_callbacks,
):
    """A lazy recalc-on-view before the async task must not steal the delta.

    The task runs after commit, so a user can view the affected list first. That
    view recalculates and writes the new rating_current WITHOUT recording an
    action. Because the pre-change baseline is snapshotted synchronously at
    enqueue time, the task must still record the CONTENT_COST_CHANGE action.
    (Regression: previously the delta was read from the already-updated
    rating_current, computed as zero, and the action was silently dropped.)
    """
    lst = _clean_list_with_equipment(make_list, make_list_fighter, cost_equipment)
    before = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()

    # Change the cost via the real signal flow, but hold the on_commit enqueue so
    # we can interleave a view before the task runs. The pre-change snapshot is
    # captured synchronously inside the post_save handler (not in the callback).
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        cost_equipment.cost = "150"
        cost_equipment.save()

    # The racing view: viewing a dirty list recalculates and writes the new
    # rating_current (this is what get_clean_list_or_404 does), clearing dirty.
    lst.refresh_from_db()
    assert lst.dirty is True
    lst.facts_from_db(update=True)
    lst.refresh_from_db()
    assert lst.dirty is False

    # Now the deferred enqueue fires; under ImmediateBackend the task runs inline.
    for cb in callbacks:
        cb()

    after = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()
    assert after == before + 1


@pytest.mark.django_db
def test_idempotent_after_view_race(make_list, make_list_fighter, cost_equipment):
    """A redelivery carrying the same frozen snapshot must not duplicate the
    action or re-apply credits, even when a view recalculated the list first."""
    lst = _clean_list_with_equipment(make_list, make_list_fighter, cost_equipment)
    old_rating = lst.rating_current
    old_stash = lst.stash_current

    ContentEquipment = cost_equipment.__class__
    ContentEquipment.objects.filter(pk=cost_equipment.pk).update(cost="150")
    cost_equipment.refresh_from_db()
    cost_equipment.set_dirty()
    lst.facts_from_db(update=True)  # the racing view moves rating_current

    # The snapshot captured synchronously at enqueue time holds the pre-change
    # baseline; the same payload is delivered on a redelivery.
    snapshot = {str(lst.id): [old_rating, old_stash]}
    ct = ContentType.objects.get_for_model(ContentEquipment)

    propagate_content_cost_change.enqueue(
        content_type_id=ct.id,
        object_id=str(cost_equipment.pk),
        before_snapshots=snapshot,
    )
    after_first = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()

    propagate_content_cost_change.enqueue(
        content_type_id=ct.id,
        object_id=str(cost_equipment.pk),
        before_snapshots=snapshot,
    )
    after_second = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()

    assert after_first == 1
    assert after_second == after_first


@pytest.mark.django_db
def test_sweep_failure_enqueues_background_heal(
    make_list, make_list_fighter, cost_equipment
):
    """A list the sweep fails on gets a background heal enqueued (#1860 Stage B).

    Index pages show last-good cached numbers and never recompute, so without
    this a sweep-failed list would display stale wealth until someone opened
    its detail page. The heal refreshes caches only — the audit action for the
    change is still lost, and a redelivery remains the real recovery.
    """
    lst = _clean_list_with_equipment(make_list, make_list_fighter, cost_equipment)

    ContentEquipment = cost_equipment.__class__
    ContentEquipment.objects.filter(pk=cost_equipment.pk).update(cost="150")
    cost_equipment.refresh_from_db()
    cost_equipment.set_dirty()

    from gyrinx.content.models.signal_handlers import (
        _create_content_cost_change_actions,
    )

    with (
        patch(
            "gyrinx.core.cost.pin_sweep.rewrite_pinned_amounts_for_list",
            side_effect=RuntimeError("boom"),
        ),
        patch("gyrinx.core.tasks.refresh_list_facts") as mock_task,
    ):
        _create_content_cost_change_actions(cost_equipment)

    mock_task.enqueue.assert_called_once_with(list_id=str(lst.pk))

    # The per-list transaction rolled back: no action was recorded.
    assert not ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).exists()


# ---------------------------------------------------------------------------
# Chaos: drive the real signal → on_commit → enqueue path through the durable
# local backend (manual mode) and inject at-least-once redelivery, transient
# failure, and message loss. These exercise the SEQUENTIAL idempotency guards
# under conditions that only production Pub/Sub used to reach.
# ---------------------------------------------------------------------------


def _campaign_list_with_equipment(make_list, make_list_fighter, cost_equipment):
    """A campaign-mode gang with the equipment on an active fighter, so a content
    cost change moves rating and charges/refunds campaign credits."""
    lst = make_list("Campaign Gang", status=List.CAMPAIGN_MODE)
    lst.credits_current = 500
    lst.save()
    fighter = make_list_fighter(lst, "Test Fighter")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=cost_equipment,
    )
    lst.facts_from_db(update=True)
    lst.refresh_from_db()
    return lst


def _cost_change_actions(lst):
    return ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()


@pytest.mark.django_db
def test_chaos_redelivery_does_not_double_charge_campaign_credits(
    task_queue, make_list, make_list_fighter, cost_equipment
):
    """At-least-once redelivery of a cost change must charge campaign credits
    exactly once. Guards the snapshot dedup (subject + pre-change baseline)
    against a duplicate delivery carrying the same frozen snapshot."""
    lst = _campaign_list_with_equipment(make_list, make_list_fighter, cost_equipment)
    credits_before = lst.credits_current

    # Real flow: saving the new cost fires the signal, which snapshots baselines
    # synchronously and enqueues the task on commit.
    with task_queue.capture():
        cost_equipment.cost = "150"  # +50
        cost_equipment.save()
    task_queue.deliver_all()

    lst.refresh_from_db()
    credits_after_first = lst.credits_current
    actions_after_first = _cost_change_actions(lst)
    assert credits_after_first == credits_before - 50  # charged once
    assert actions_after_first == 1

    # Duplicate delivery of the SAME message (same frozen snapshot).
    task_queue.redeliver_last(task_name="propagate_content_cost_change")

    lst.refresh_from_db()
    assert lst.credits_current == credits_after_first  # not charged twice
    assert _cost_change_actions(lst) == actions_after_first


@pytest.mark.django_db
def test_chaos_transient_failure_then_retry_charges_once(
    task_queue, make_list, make_list_fighter, cost_equipment
):
    """A nacked first delivery followed by a retry must land the credit charge
    exactly once — not zero (lost) and not twice (double-charged)."""
    lst = _campaign_list_with_equipment(make_list, make_list_fighter, cost_equipment)
    credits_before = lst.credits_current

    with task_queue.capture():
        cost_equipment.cost = "150"  # +50
        cost_equipment.save()

    # First delivery of the propagate task fails; deliver_all retries it.
    task_queue.fail_next(1)
    task_queue.deliver_all()

    lst.refresh_from_db()
    assert lst.credits_current == credits_before - 50
    assert _cost_change_actions(lst) == 1


@pytest.mark.django_db
def test_chaos_dropped_delivery_loses_action_but_leaves_list_dirty(
    task_queue, make_list, make_list_fighter, cost_equipment
):
    """A dropped (lost) delivery applies nothing — documenting the fire-and-forget
    loss window. The list is left dirty so a later heal/redelivery still recovers
    the cached numbers (the audit action stays lost until a redelivery, by design)."""
    lst = _campaign_list_with_equipment(make_list, make_list_fighter, cost_equipment)
    credits_before = lst.credits_current

    with task_queue.capture():
        cost_equipment.cost = "150"
        cost_equipment.save()

    # Drop every queued delivery for this change (propagate + any refresh).
    task_queue.drop_next(10)
    task_queue.deliver_all()

    lst.refresh_from_db()
    # No action, no credit movement — the change was lost in flight.
    assert _cost_change_actions(lst) == 0
    assert lst.credits_current == credits_before
    # But the list is still marked dirty, so it is not silently stuck on stale
    # cached numbers — a dirty list heals on next view or redelivery.
    assert lst.dirty is True
