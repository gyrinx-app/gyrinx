"""
Tests for fighter edit handlers.

These tests directly test the handler functions in gyrinx.core.handlers.fighter.edit,
ensuring that business logic works correctly without involving HTTP machinery.

The handler API expects:
1. The fighter already has NEW values applied (e.g., by ModelForm's is_valid())
2. OLD values are passed to the handler for comparison
"""

import pytest

from gyrinx.content.models import ContentEquipmentFighterProfile
from gyrinx.core.handlers.fighter import handle_fighter_edit
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment
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
def test_handle_fighter_edit_child_fighter_on_stash(
    user, make_list, make_content_fighter, content_house, make_equipment, settings
):
    """Test that cost changes for child fighter (vehicle) on stash go to stash_delta.

    This tests the _is_fighter_stash_linked() logic that handles child fighters
    (vehicles/exotic beasts) whose parent equipment is on a stash fighter.
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.stash_current = 200
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

    # Create vehicle equipment with fighter profile
    vehicle_equipment = make_equipment("Test Vehicle", cost="150")
    vehicle_fighter_type = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=150,
    )
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment,
        content_fighter=vehicle_fighter_type,
    )

    # Create equipment assignment on stash fighter
    equipment_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash_fighter,
        content_equipment=vehicle_equipment,
    )

    # Create child fighter linked to equipment on stash
    child_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=vehicle_fighter_type,
        name="Child Vehicle",
    )
    child_fighter.source_assignment.add(equipment_assignment)

    # Simulate form setting cost override on child fighter
    child_fighter.cost_override = 200

    # Call handler with old value (None)
    result = handle_fighter_edit(
        user=user,
        fighter=child_fighter,
        old_cost_override=None,
    )

    # Delta = 200 - 150 = +50
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


@pytest.mark.django_db
def test_handle_fighter_edit_cost_override_propagates_to_fighter_rating_current(
    user, make_list, content_fighter, settings
):
    """Test that cost_override changes propagate to fighter.rating_current."""
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

    # Fighter starts with rating_current = 0 (just created)
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current

    # Simulate form applying new value: set override to 150
    fighter.cost_override = 150

    # Call handler with old value (None)
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_cost_override=None,
    )

    # Delta = 150 - 100 = +50
    assert result.changes[0].rating_delta == 50

    # Verify fighter.rating_current propagated (+50)
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating + 50


@pytest.mark.django_db
def test_handle_fighter_edit_cost_override_clear_propagates_to_fighter_rating_current(
    user, make_list, content_fighter, settings
):
    """Test that clearing cost_override propagates negative delta to fighter.rating_current."""
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

    # Set initial rating_current manually
    fighter.rating_current = 150
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current

    # Simulate form clearing override
    fighter.cost_override = None

    # Call handler with old value (150)
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_cost_override=150,
    )

    # Delta = 100 - 150 = -50
    assert result.changes[0].rating_delta == -50

    # Verify fighter.rating_current propagated (-50)
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating - 50


@pytest.mark.django_db
def test_handle_fighter_edit_content_fighter_change(
    user, make_list, make_content_fighter, content_house, settings
):
    """Test that changing content_fighter creates ListAction with correct delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create two different fighter types with different costs
    old_fighter_type = make_content_fighter(
        type="OldType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=100,
    )
    new_fighter_type = make_content_fighter(
        type="NewType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=150,
    )

    # Create fighter with old type
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=old_fighter_type,
        list=lst,
        owner=user,
    )

    # Simulate form changing content_fighter
    fighter.content_fighter = new_fighter_type

    # Call handler with old value
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_content_fighter=old_fighter_type,
    )

    assert result is not None
    assert len(result.changes) == 1
    assert result.changes[0].field_name == "content_fighter"
    assert result.changes[0].old_value == old_fighter_type
    assert result.changes[0].new_value == new_fighter_type
    # Delta = 150 - 100 = +50
    assert result.changes[0].rating_delta == 50

    # Verify ListAction created with correct delta
    assert len(result.list_actions) == 1
    assert result.list_actions[0].rating_delta == 50
    assert result.list_actions[0].stash_delta == 0
    assert "+50" in result.list_actions[0].description

    # Verify fighter updated
    fighter.refresh_from_db()
    assert fighter.content_fighter == new_fighter_type


@pytest.mark.django_db
def test_handle_fighter_edit_content_fighter_change_propagates_to_fighter_rating_current(
    user, make_list, make_content_fighter, content_house, settings
):
    """Test that content_fighter changes propagate to fighter.rating_current."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create two different fighter types with different costs
    old_fighter_type = make_content_fighter(
        type="OldType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=100,
    )
    new_fighter_type = make_content_fighter(
        type="NewType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=150,
    )

    # Create fighter with old type
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=old_fighter_type,
        list=lst,
        owner=user,
    )

    # Set initial rating_current
    fighter.rating_current = 100
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current

    # Simulate form changing content_fighter
    fighter.content_fighter = new_fighter_type

    # Call handler with old value
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_content_fighter=old_fighter_type,
    )

    # Delta = 150 - 100 = +50
    assert result.changes[0].rating_delta == 50

    # Verify fighter.rating_current propagated (+50)
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating + 50


@pytest.mark.django_db
def test_handle_fighter_edit_content_fighter_change_with_cost_override(
    user, make_list, make_content_fighter, content_house, settings
):
    """Test that content_fighter change doesn't affect cost when cost_override is set."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create two different fighter types with different costs
    old_fighter_type = make_content_fighter(
        type="OldType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=100,
    )
    new_fighter_type = make_content_fighter(
        type="NewType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=150,
    )

    # Create fighter with old type and cost_override
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=old_fighter_type,
        list=lst,
        owner=user,
        cost_override=200,  # Override is set, so base cost doesn't matter
    )

    # Simulate form changing content_fighter
    fighter.content_fighter = new_fighter_type

    # Call handler with old value
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_content_fighter=old_fighter_type,
    )

    assert result is not None
    assert len(result.changes) == 1
    assert result.changes[0].field_name == "content_fighter"
    # Delta should be 0 because cost_override takes precedence
    assert result.changes[0].rating_delta == 0
    assert result.changes[0].stash_delta == 0

    # Description should NOT include cost delta
    assert "+0" not in result.list_actions[0].description
    assert "¢" not in result.list_actions[0].description


@pytest.mark.django_db
def test_handle_fighter_edit_content_fighter_change_to_cheaper(
    user, make_list, make_content_fighter, content_house, settings
):
    """Test that changing to a cheaper content_fighter creates negative delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create two different fighter types with different costs
    old_fighter_type = make_content_fighter(
        type="ExpensiveType",
        category=FighterCategoryChoices.CHAMPION,
        house=content_house,
        base_cost=200,
    )
    new_fighter_type = make_content_fighter(
        type="CheapType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=50,
    )

    # Create fighter with expensive type
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=old_fighter_type,
        list=lst,
        owner=user,
    )

    # Set initial rating_current
    fighter.rating_current = 200
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current

    # Simulate form changing content_fighter to cheaper type
    fighter.content_fighter = new_fighter_type

    # Call handler with old value
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_content_fighter=old_fighter_type,
    )

    # Delta = 50 - 200 = -150
    assert result.changes[0].rating_delta == -150
    assert "-150" in result.list_actions[0].description

    # Verify fighter.rating_current propagated (-150)
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating - 150


@pytest.mark.django_db
def test_handle_fighter_edit_content_fighter_change_to_stash_type(
    user, make_list, make_content_fighter, content_house, settings
):
    """Test that changing to a stash content_fighter routes delta to stash."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 100
    lst.stash_current = 200
    lst.save()

    # Create a regular fighter type
    regular_fighter_type = make_content_fighter(
        type="Regular",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=50,
    )

    # Create a stash fighter type
    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )

    fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=regular_fighter_type,
        list=lst,
        owner=user,
    )

    # Simulate form changing content_fighter to stash type
    fighter.content_fighter = stash_fighter_type

    # Call handler with old value
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_content_fighter=regular_fighter_type,
    )

    # Delta = 0 - 50 = -50, goes to stash because new content_fighter is stash-linked
    assert result is not None
    assert result.changes[0].stash_delta == -50
    assert result.changes[0].rating_delta == 0
    assert result.list_actions[0].stash_delta == -50
    assert result.list_actions[0].rating_delta == 0


@pytest.mark.django_db
def test_handle_fighter_edit_content_fighter_and_cost_override_change_simultaneously(
    user, make_list, make_content_fighter, content_house, settings
):
    """Test that changing both content_fighter and cost_override correctly calculates delta.

    This is a critical edge case: when both fields change in the same edit, the delta
    should be calculated as:
      new_effective_cost - old_effective_cost

    Where:
    - old_effective_cost = old_cost_override (if set) or old_content_fighter.cost
    - new_effective_cost = new_cost_override (if set) or new_content_fighter.cost

    Scenario: Fighter A (100) with no override -> Fighter B (150) with override 200
    Expected delta: 200 - 100 = +100
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create two different fighter types with different costs
    old_fighter_type = make_content_fighter(
        type="OldType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=100,
    )
    new_fighter_type = make_content_fighter(
        type="NewType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=150,
    )

    # Create fighter with old type and no override
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=old_fighter_type,
        list=lst,
        owner=user,
    )
    fighter.rating_current = 100
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current

    # Simulate form changing BOTH content_fighter AND setting cost_override
    fighter.content_fighter = new_fighter_type
    fighter.cost_override = 200

    # Call handler with old values for both fields
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_content_fighter=old_fighter_type,
        old_cost_override=None,
    )

    assert result is not None
    # Two changes: content_fighter and cost_override
    assert len(result.changes) == 2

    # Find the changes by field name
    content_fighter_change = next(
        c for c in result.changes if c.field_name == "content_fighter"
    )
    cost_override_change = next(
        c for c in result.changes if c.field_name == "cost_override"
    )

    # content_fighter delta should be 0 because cost_override is now set
    # (the override takes precedence for effective cost)
    assert content_fighter_change.rating_delta == 0

    # cost_override delta should be: 200 (new override) - 100 (old base cost) = +100
    # NOT: 200 - 150 = +50 (which would be wrong - using new content_fighter cost)
    assert cost_override_change.rating_delta == 100

    # Total delta propagated should be +100
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating + 100


@pytest.mark.django_db
def test_handle_fighter_edit_content_fighter_change_and_cost_override_clear_simultaneously(
    user, make_list, make_content_fighter, content_house, settings
):
    """Test clearing cost_override while changing content_fighter.

    Scenario: Fighter A (100) with override 200 -> Fighter B (150) with no override
    Expected delta: 150 - 200 = -50
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create two different fighter types with different costs
    old_fighter_type = make_content_fighter(
        type="OldType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=100,
    )
    new_fighter_type = make_content_fighter(
        type="NewType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=150,
    )

    # Create fighter with old type and cost override
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=old_fighter_type,
        list=lst,
        owner=user,
        cost_override=200,
    )
    fighter.rating_current = 200
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current

    # Simulate form changing content_fighter AND clearing cost_override
    fighter.content_fighter = new_fighter_type
    fighter.cost_override = None

    # Call handler with old values for both fields
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_content_fighter=old_fighter_type,
        old_cost_override=200,
    )

    assert result is not None
    assert len(result.changes) == 2

    # Find the changes by field name
    content_fighter_change = next(
        c for c in result.changes if c.field_name == "content_fighter"
    )
    cost_override_change = next(
        c for c in result.changes if c.field_name == "cost_override"
    )

    # content_fighter delta should be 0 because cost_override WAS set before
    # (the old effective cost was determined by the override, not the content_fighter)
    assert content_fighter_change.rating_delta == 0

    # cost_override delta should be: 150 (new base cost, no override) - 200 (old override) = -50
    assert cost_override_change.rating_delta == -50

    # Total delta propagated should be -50
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating - 50


@pytest.mark.django_db
def test_handle_fighter_edit_content_fighter_change_with_existing_override_unchanged(
    user, make_list, make_content_fighter, content_house, settings
):
    """Test changing content_fighter when there's an existing cost_override that doesn't change.

    Scenario: Fighter A (100) with override 200 -> Fighter B (150) with override 200 (unchanged)
    Expected delta: 0 (override is still 200, effective cost unchanged)
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create two different fighter types with different costs
    old_fighter_type = make_content_fighter(
        type="OldType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=100,
    )
    new_fighter_type = make_content_fighter(
        type="NewType",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=150,
    )

    # Create fighter with old type and cost override
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=old_fighter_type,
        list=lst,
        owner=user,
        cost_override=200,
    )
    fighter.rating_current = 200
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current

    # Simulate form changing ONLY content_fighter (cost_override stays 200)
    fighter.content_fighter = new_fighter_type

    # Call handler - only providing old_content_fighter, not old_cost_override
    result = handle_fighter_edit(
        user=user,
        fighter=fighter,
        old_content_fighter=old_fighter_type,
    )

    assert result is not None
    assert len(result.changes) == 1
    assert result.changes[0].field_name == "content_fighter"

    # content_fighter delta should be 0 because cost_override is set
    assert result.changes[0].rating_delta == 0

    # No change in effective cost
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating
