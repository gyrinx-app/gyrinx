"""
Tests for background tasks in gyrinx.core.tasks.
"""

import uuid

import pytest

from gyrinx.core.tasks import refresh_list_facts


@pytest.mark.django_db
def test_refresh_list_facts_updates_dirty_list(user, make_list, content_fighter):
    """Test that refresh_list_facts clears the dirty flag and updates cached values."""
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Test List")
    lst.dirty = True
    lst.rating_current = 0
    lst.save()

    # Create a fighter to have some rating
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    expected_rating = fighter.cost_int()

    # Call the task directly (not via enqueue, to test the function itself)
    refresh_list_facts.func(list_id=str(lst.pk))

    # Verify list was updated
    lst.refresh_from_db()
    assert lst.dirty is False
    assert lst.rating_current == expected_rating


@pytest.mark.django_db
def test_refresh_list_facts_handles_missing_list():
    """Test that refresh_list_facts handles non-existent list gracefully."""
    fake_id = str(uuid.uuid4())

    # Should not raise - just logs a warning
    refresh_list_facts.func(list_id=fake_id)


@pytest.mark.django_db
def test_refresh_list_facts_via_enqueue(user, make_list, content_fighter):
    """Test that refresh_list_facts works when called via enqueue (ImmediateBackend)."""
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Test List")
    lst.dirty = True
    lst.rating_current = 0
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    expected_rating = fighter.cost_int()

    # Use enqueue (runs synchronously with ImmediateBackend)
    refresh_list_facts.enqueue(list_id=str(lst.pk))

    # Verify list was updated
    lst.refresh_from_db()
    assert lst.dirty is False
    assert lst.rating_current == expected_rating
