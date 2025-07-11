"""Test that Events with list_id update the list's modified timestamp."""

from datetime import timedelta

import pytest
from django.utils import timezone

from gyrinx.core.models.events import Event, EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_event_with_list_id_updates_list_modified(make_list):
    """Test that creating an event with list_id updates the list's modified timestamp."""
    # Create a list with an old modified timestamp
    lst = make_list("Test List")

    # Force the list to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    List.objects.filter(id=lst.id).update(modified=old_modified)

    # Refresh from DB to get the updated timestamp
    lst.refresh_from_db()
    assert lst.modified < timezone.now() - timedelta(hours=1)

    # Create an event with list_id in context
    event = Event.objects.create(
        owner=lst.owner,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        context={
            "list_id": str(lst.id),
            "list_name": lst.name,
            "fighter_name": "Test Fighter",
        },
    )

    # Refresh the list from DB
    lst.refresh_from_db()

    # The list's modified timestamp should now match the event's created timestamp
    assert lst.modified == event.created


@pytest.mark.django_db
def test_event_without_list_id_does_not_update_list(make_list):
    """Test that events without list_id don't update any list."""
    # Create a list
    lst = make_list("Test List")

    # Force the list to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    List.objects.filter(id=lst.id).update(modified=old_modified)

    # Create an event without list_id
    Event.objects.create(
        owner=lst.owner,
        noun=EventNoun.USER,
        verb=EventVerb.LOGIN,
        context={"some_other_data": "value"},
    )

    # Refresh the list from DB
    lst.refresh_from_db()

    # The list's modified timestamp should not have changed
    assert lst.modified < timezone.now() - timedelta(hours=1)


@pytest.mark.django_db
def test_event_with_empty_list_id_does_not_update_list(make_list):
    """Test that events with empty list_id don't update any list."""
    # Create a list
    lst = make_list("Test List")

    # Force the list to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    List.objects.filter(id=lst.id).update(modified=old_modified)

    # Create an event with empty list_id
    Event.objects.create(
        owner=lst.owner,
        noun=EventNoun.LIST,
        verb=EventVerb.UPDATE,
        context={"list_id": "", "other_data": "value"},
    )

    # Refresh the list from DB
    lst.refresh_from_db()

    # The list's modified timestamp should not have changed
    assert lst.modified < timezone.now() - timedelta(hours=1)


@pytest.mark.django_db
def test_event_with_nonexistent_list_id_does_not_error(user):
    """Test that events with non-existent list_id don't cause errors."""

    # Create an event with a non-existent list_id
    # This should not raise an exception
    Event.objects.create(
        owner=user,
        noun=EventNoun.LIST,
        verb=EventVerb.UPDATE,
        context={
            "list_id": "00000000-0000-0000-0000-000000000000",
            "list_name": "Non-existent List",
        },
    )
    # Test passes if no exception is raised


@pytest.mark.django_db
def test_log_event_helper_updates_list_modified(make_list):
    """Test that using the log_event helper also triggers list updates."""
    # Create a list
    lst = make_list("Test List")

    # Force the list to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    List.objects.filter(id=lst.id).update(modified=old_modified)

    # Use log_event helper with list_id
    log_event(
        user=lst.owner,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.CREATE,
        request=None,
        fighter_name="New Fighter",
        list_id=str(lst.id),
        list_name=lst.name,
    )

    # Refresh the list from DB
    lst.refresh_from_db()

    # The list's modified timestamp should be recent
    assert lst.modified > timezone.now() - timedelta(seconds=5)


@pytest.mark.django_db
def test_updating_existing_event_does_not_update_list(make_list):
    """Test that updating an existing event doesn't update the list's modified timestamp."""
    # Create a list and event
    lst = make_list("Test List")

    # Create an event with list_id
    event = Event.objects.create(
        owner=lst.owner,
        noun=EventNoun.LIST,
        verb=EventVerb.UPDATE,
        context={"list_id": str(lst.id), "list_name": lst.name},
    )

    # Force the list to have an old modified timestamp
    old_modified = timezone.now() - timedelta(hours=2)
    List.objects.filter(id=lst.id).update(modified=old_modified)

    # Update the existing event
    event.context["updated_field"] = "new_value"
    event.save()

    # Refresh the list from DB
    lst.refresh_from_db()

    # The list's modified timestamp should not have changed
    assert lst.modified < timezone.now() - timedelta(hours=1)
