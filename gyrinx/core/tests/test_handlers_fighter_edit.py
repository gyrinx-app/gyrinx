"""
Tests for fighter edit handlers.

These tests directly test the handler functions in gyrinx.core.handlers.fighter.edit,
ensuring that business logic works correctly without involving HTTP machinery.

The handler API expects:
1. The fighter already has NEW values applied (e.g., by ModelForm's is_valid())
2. OLD values are passed to the handler for comparison
"""

import pytest

from gyrinx.core.handlers.fighter import handle_fighter_edit
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.list import ListFighter
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_handle_fighter_edit_no_changes(user, make_list, content_fighter, settings):
    """Test that handler returns None when no fields change."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Call with old values same as current - no changes
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_name="Test Fighter",
        old_content_fighter=content_fighter,
    )

    assert result is None


@pytest.mark.django_db
def test_handle_fighter_edit_name_change(user, make_list, content_fighter, settings):
    """Test that changing name creates a ListAction with zero deltas."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Old Name",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Simulate form applying new value
    fighter.name = "New Name"

    # Call handler with old value
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_name="Old Name",
    )

    assert result is not None
    assert len(result.changes) == 1
    assert result.changes[0].field_name == "name"
    assert result.changes[0].old_value == "Old Name"
    assert result.changes[0].new_value == "New Name"
    assert result.changes[0].rating_delta == 0
    assert result.changes[0].stash_delta == 0

    # Verify ListAction created
    assert len(result.list_actions) == 1
    assert result.list_actions[0].action_type == ListActionType.UPDATE_FIGHTER
    assert result.list_actions[0].rating_delta == 0
    assert result.list_actions[0].stash_delta == 0
    assert "Renamed" in result.list_actions[0].description

    # Verify fighter updated (saved by handler)
    fighter.refresh_from_db()
    assert fighter.name == "New Name"


@pytest.mark.django_db
def test_handle_fighter_edit_cost_override_set(
    user, make_list, content_fighter, settings
):
    """Test that setting cost_override creates ListAction with correct delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # content_fighter has base_cost=100
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Simulate form applying new value: set override to 150
    fighter.cost_override = 150

    # Call handler with old value (None - no override was set)
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_cost_override=None,
    )

    assert result is not None
    assert len(result.changes) == 1
    assert result.changes[0].field_name == "cost_override"
    assert result.changes[0].old_value is None
    assert result.changes[0].new_value == 150
    # Delta = 150 - 100 (calculated cost) = +50
    assert result.changes[0].rating_delta == 50

    # Verify ListAction created with correct delta
    assert len(result.list_actions) == 1
    assert result.list_actions[0].rating_delta == 50
    assert result.list_actions[0].stash_delta == 0
    assert "+50" in result.list_actions[0].description

    # Verify fighter updated
    fighter.refresh_from_db()
    assert fighter.cost_override == 150


@pytest.mark.django_db
def test_handle_fighter_edit_cost_override_clear(
    user, make_list, content_fighter, settings
):
    """Test that clearing cost_override creates ListAction with negative delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 650
    lst.save()

    # content_fighter has base_cost=100, override set to 150
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        cost_override=150,
    )

    # Simulate form clearing override
    fighter.cost_override = None

    # Call handler with old value (150)
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_cost_override=150,
    )

    assert result is not None
    assert len(result.changes) == 1
    assert result.changes[0].field_name == "cost_override"
    assert result.changes[0].old_value == 150
    assert result.changes[0].new_value is None
    # Delta = 100 (calculated cost) - 150 = -50
    assert result.changes[0].rating_delta == -50

    # Verify ListAction
    assert result.list_actions[0].rating_delta == -50
    assert "-50" in result.list_actions[0].description

    # Verify fighter updated
    fighter.refresh_from_db()
    assert fighter.cost_override is None


@pytest.mark.django_db
def test_handle_fighter_edit_cost_override_change(
    user, make_list, content_fighter, settings
):
    """Test that changing cost_override value creates correct delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 600
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        cost_override=100,
    )

    # Simulate form changing override from 100 to 120
    fighter.cost_override = 120

    # Call handler with old value (100)
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_cost_override=100,
    )

    assert result is not None
    # Delta = 120 - 100 = +20
    assert result.changes[0].rating_delta == 20
    assert result.list_actions[0].rating_delta == 20


@pytest.mark.django_db
def test_handle_fighter_edit_category_override(
    user, make_list, content_fighter, settings
):
    """Test that changing category_override creates ListAction with zero delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Simulate form setting category override
    fighter.category_override = FighterCategoryChoices.CHAMPION

    # Call handler with old value (None/empty)
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_category_override="",
    )

    assert result is not None
    assert len(result.changes) == 1
    assert result.changes[0].field_name == "category_override"
    assert result.changes[0].rating_delta == 0  # Category doesn't affect cost

    # Verify fighter updated
    fighter.refresh_from_db()
    assert fighter.category_override == FighterCategoryChoices.CHAMPION


@pytest.mark.django_db
def test_handle_fighter_edit_multiple_changes(
    user, make_list, content_fighter, settings
):
    """Test that multiple field changes create multiple ListActions."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Old Name",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Simulate form changing name and setting cost override
    fighter.name = "New Name"
    fighter.cost_override = 150

    # Call handler with old values
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_name="Old Name",
        old_cost_override=None,
    )

    assert result is not None
    assert len(result.changes) == 2
    assert len(result.list_actions) == 2

    # Find the changes by field name
    name_change = next(c for c in result.changes if c.field_name == "name")
    cost_change = next(c for c in result.changes if c.field_name == "cost_override")

    assert name_change.rating_delta == 0
    assert cost_change.rating_delta == 50


@pytest.mark.django_db
def test_handle_fighter_edit_stash_fighter(
    user, make_list, make_content_fighter, content_house, settings
):
    """Test that cost changes for stash fighter go to stash_delta, not rating_delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.stash_current = 100
    lst.save()

    # Create a stash fighter type
    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )

    stash_fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_fighter_type,
        list=lst,
        owner=user,
    )

    # Simulate form setting cost override on stash
    stash_fighter.cost_override = 50

    # Call handler with old value (None)
    result = handle_fighter_edit(
        user=user,
        fighter=stash_fighter,
        old_cost_override=None,
    )

    assert result is not None
    assert result.changes[0].stash_delta == 50
    assert result.changes[0].rating_delta == 0
    assert result.list_actions[0].stash_delta == 50
    assert result.list_actions[0].rating_delta == 0


@pytest.mark.django_db
def test_handle_fighter_edit_feature_flag_disabled(
    user, make_list, content_fighter, settings
):
    """Test that handler still works but returns None for list_action when flag disabled."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = False
    lst = make_list("Test List", create_initial_action=False)

    fighter = ListFighter.objects.create(
        name="Old Name",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Simulate form changing name
    fighter.name = "New Name"

    # Call handler with old value
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_name="Old Name",
    )

    # Result should still be returned with changes tracked
    assert result is not None
    assert len(result.changes) == 1
    # But list_action may be None if create_action returns None
    # The handler still works, it just doesn't create ListAction

    # Fighter should still be updated
    fighter.refresh_from_db()
    assert fighter.name == "New Name"
