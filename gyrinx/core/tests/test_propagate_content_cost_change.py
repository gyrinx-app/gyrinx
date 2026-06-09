"""Tests for the async content-cost-change propagation task and its enqueue."""

from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import ListFighterEquipmentAssignment
from gyrinx.core.tasks import propagate_content_cost_change


@pytest.fixture
def cost_equipment(make_equipment):
    """Equipment with a known cost, in a real category."""
    return make_equipment("Boltgun", cost="100", category="Weapons & Ammo")


def _clean_list_with_equipment(make_list, make_list_fighter, cost_equipment):
    lst = make_list("Test List", create_initial_action=True)
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
    make_list, make_list_fighter, cost_equipment, settings
):
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
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
def test_task_idempotent_on_second_run(
    make_list, make_list_fighter, cost_equipment, settings
):
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
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
