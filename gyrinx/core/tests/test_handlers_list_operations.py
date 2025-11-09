"""
Tests for list operation handlers.

These tests directly test the handle_list_creation function in
gyrinx.core.handlers.list_operations, ensuring that business logic works
correctly without involving HTTP machinery.
"""

import pytest
from django.conf import settings

from gyrinx.content.models import ContentFighter
from gyrinx.core.handlers.list_operations import handle_list_creation
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import List, ListFighter


@pytest.mark.django_db
def test_handle_list_creation_with_stash(user, content_house):
    """Test list creation with stash fighter."""
    # Create list instance (not saved yet)
    lst = List(
        owner=user,
        content_house=content_house,
        name="Test List",
    )

    # Call the handler
    result = handle_list_creation(
        user=user,
        lst=lst,
        create_stash=True,
    )

    # Verify list was saved
    assert result.lst.id is not None
    assert List.objects.filter(id=result.lst.id).exists()

    # Verify stash fighter was created
    assert result.stash_fighter is not None
    assert result.stash_fighter.name == "Stash"
    assert result.stash_fighter.content_fighter.is_stash is True
    assert result.stash_fighter.list == result.lst
    assert ListFighter.objects.filter(id=result.stash_fighter.id).exists()

    # Verify initial action created (if feature flag enabled)
    if settings.FEATURE_LIST_ACTION_CREATE_INITIAL:
        assert result.initial_action is not None
        assert result.initial_action.action_type == ListActionType.CREATE
        assert result.initial_action.description == "List created"
    else:
        assert result.initial_action is None


@pytest.mark.django_db
def test_handle_list_creation_without_stash(user, content_house):
    """Test list creation without stash fighter."""
    lst = List(
        owner=user,
        content_house=content_house,
        name="Test List",
    )

    result = handle_list_creation(
        user=user,
        lst=lst,
        create_stash=False,
    )

    # Verify list was saved
    assert result.lst.id is not None

    # Verify no stash fighter was created
    assert result.stash_fighter is None
    assert not ListFighter.objects.filter(
        list=result.lst, content_fighter__is_stash=True
    ).exists()


@pytest.mark.django_db
def test_handle_list_creation_initial_action_disabled(user, content_house, settings):
    """Test that no initial action is created when feature flag is disabled."""
    # Disable the feature flag
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = False

    lst = List(
        owner=user,
        content_house=content_house,
        name="Test List",
    )

    result = handle_list_creation(
        user=user,
        lst=lst,
        create_stash=True,
    )

    # Verify no initial action created
    assert result.initial_action is None
    assert not ListAction.objects.filter(list=result.lst).exists()


@pytest.mark.django_db
def test_handle_list_creation_stash_fighter_reused(user, content_house):
    """Test that existing stash ContentFighter is reused."""
    # Create a stash ContentFighter manually
    existing_stash, _ = ContentFighter.objects.get_or_create(
        house=content_house,
        is_stash=True,
        defaults={
            "type": "Stash",
            "category": "STASH",
            "base_cost": 0,
        },
    )

    # Create first list with stash
    lst1 = List(
        owner=user,
        content_house=content_house,
        name="Test List 1",
    )
    result1 = handle_list_creation(
        user=user,
        lst=lst1,
        create_stash=True,
    )

    # Create second list with stash
    lst2 = List(
        owner=user,
        content_house=content_house,
        name="Test List 2",
    )
    result2 = handle_list_creation(
        user=user,
        lst=lst2,
        create_stash=True,
    )

    # Verify both stash fighters use the same ContentFighter
    assert (
        result1.stash_fighter.content_fighter == result2.stash_fighter.content_fighter
    )
    assert result1.stash_fighter.content_fighter == existing_stash

    # Verify there's only one stash ContentFighter for this house
    assert (
        ContentFighter.objects.filter(house=content_house, is_stash=True).count() == 1
    )


@pytest.mark.django_db
def test_handle_list_creation_transaction_rollback(user, content_house, monkeypatch):
    """Test that transaction rolls back on error."""
    lst = List(
        owner=user,
        content_house=content_house,
        name="Test List",
    )

    # Count initial objects
    initial_list_count = List.objects.count()
    initial_fighter_count = ListFighter.objects.count()

    # Monkeypatch ListFighter.objects.create to raise an error
    def failing_create(*args, **kwargs):
        raise RuntimeError("Simulated error")

    monkeypatch.setattr(ListFighter.objects, "create", failing_create)

    # Call the handler - should raise error and rollback
    with pytest.raises(RuntimeError):
        handle_list_creation(
            user=user,
            lst=lst,
            create_stash=True,
        )

    # Verify transaction rolled back - no new objects created
    assert List.objects.count() == initial_list_count
    assert ListFighter.objects.count() == initial_fighter_count
