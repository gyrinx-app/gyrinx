"""
Tests for vehicle purchase handlers.

These tests directly test the handle_vehicle_purchase function in
gyrinx.core.handlers.equipment_purchases, ensuring that business logic works
correctly without involving HTTP machinery.
"""

import pytest
from django.core.exceptions import ValidationError

from gyrinx.core.handlers.equipment_purchases import handle_vehicle_purchase
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_vehicle_purchase_campaign_mode_with_crew(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test vehicle purchase with crew in campaign mode."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.save()

    # Create vehicle fighter (category=VEHICLE makes is_vehicle property True)
    vehicle_fighter = make_content_fighter(
        type="Ridgehauler",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=180,
    )

    # Create crew fighter
    crew_fighter = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    # Create vehicle equipment
    vehicle_equipment = make_equipment("Ridgehauler", cost="180", category="Vehicles")

    # Call the handler
    result = handle_vehicle_purchase(
        user=user,
        lst=lst,
        vehicle_equipment=vehicle_equipment,
        vehicle_fighter=vehicle_fighter,
        crew_fighter=crew_fighter,
        crew_name="Test Crew",
        is_stash=False,
    )

    # Verify result
    assert result.vehicle_cost == 180
    assert result.crew_cost == 50
    assert result.total_cost == 230
    assert result.is_stash is False
    assert "Purchased Ridgehauler and crew Test Crew (230¢)" in result.description

    # Verify crew fighter created
    assert result.crew_fighter is not None
    assert result.crew_fighter.name == "Test Crew"
    assert result.crew_fighter.content_fighter == crew_fighter

    # Verify vehicle assignment created
    assert result.vehicle_assignment is not None
    assert result.vehicle_assignment.content_equipment == vehicle_equipment
    assert result.vehicle_assignment.list_fighter == result.crew_fighter

    if feature_flag_enabled:
        # Verify crew ListAction created
        assert result.crew_list_action is not None
        assert result.crew_list_action.action_type == ListActionType.ADD_FIGHTER
        assert result.crew_list_action.rating_delta == 50
        assert result.crew_list_action.credits_delta == -50
        assert result.crew_list_action.rating_before == 500
        assert result.crew_list_action.credits_before == 1000

        # Verify vehicle ListAction created
        assert result.vehicle_list_action is not None
        assert result.vehicle_list_action.action_type == ListActionType.ADD_EQUIPMENT
        assert result.vehicle_list_action.rating_delta == 180
        assert result.vehicle_list_action.stash_delta == 0
        assert result.vehicle_list_action.credits_delta == -180
    else:
        assert result.crew_list_action is None
        assert result.vehicle_list_action is None

    # Verify CampaignAction created (always created in campaign mode)
    assert result.campaign_action is not None
    assert (
        "Purchased Ridgehauler and crew Test Crew (230¢)"
        in result.campaign_action.description
    )

    # Verify credits spent (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 770


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_vehicle_purchase_list_building_mode(
    user,
    make_list,
    content_house,
    make_content_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test vehicle purchase with crew in list building mode (no credits)."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create vehicle fighter
    vehicle_fighter = make_content_fighter(
        type="Ridgehauler",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=180,
    )

    # Create crew fighter
    crew_fighter = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    # Create vehicle equipment
    vehicle_equipment = make_equipment("Ridgehauler", cost="180", category="Vehicles")

    # Call the handler
    result = handle_vehicle_purchase(
        user=user,
        lst=lst,
        vehicle_equipment=vehicle_equipment,
        vehicle_fighter=vehicle_fighter,
        crew_fighter=crew_fighter,
        crew_name="Test Crew",
        is_stash=False,
    )

    # Verify result
    assert result.total_cost == 230
    assert result.campaign_action is None  # No campaign mode

    if feature_flag_enabled:
        # Verify ListActions created with no credit deltas
        assert result.crew_list_action.credits_delta == 0
        assert result.vehicle_list_action.credits_delta == 0

        # Verify rating deltas are correct
        assert result.crew_list_action.rating_delta == 50
        assert result.vehicle_list_action.rating_delta == 180
    else:
        assert result.crew_list_action is None
        assert result.vehicle_list_action is None

    # Verify credits unchanged (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 0


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_vehicle_purchase_stash_mode(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test vehicle purchase to stash (no crew creation)."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.stash_current = 500
    lst.save()

    # Create vehicle fighter
    vehicle_fighter = make_content_fighter(
        type="Ridgehauler",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=180,
    )

    # Create vehicle equipment
    vehicle_equipment = make_equipment("Ridgehauler", cost="180", category="Vehicles")

    # Call the handler with is_stash=True
    result = handle_vehicle_purchase(
        user=user,
        lst=lst,
        vehicle_equipment=vehicle_equipment,
        vehicle_fighter=vehicle_fighter,
        crew_fighter=None,  # No crew fighter when adding to stash
        crew_name=None,  # No crew name when adding to stash
        is_stash=True,
    )

    # Verify result
    assert result.vehicle_cost == 180
    assert result.crew_cost == 0
    assert result.total_cost == 180
    assert result.is_stash is True
    assert "Purchased Ridgehauler (180¢)" in result.description

    # Verify crew fighter is stash
    assert result.crew_fighter is not None
    assert result.crew_fighter.is_stash is True

    # Verify no crew ListAction created (only vehicle action)
    assert result.crew_list_action is None

    if feature_flag_enabled:
        # Verify vehicle ListAction uses stash delta not rating delta
        assert result.vehicle_list_action.rating_delta == 0
        assert result.vehicle_list_action.stash_delta == 180
        assert result.vehicle_list_action.credits_delta == -180
    else:
        assert result.vehicle_list_action is None

    # Verify credits spent (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 820


@pytest.mark.django_db
def test_handle_vehicle_purchase_insufficient_credits(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    make_equipment,
):
    """Test vehicle purchase fails with insufficient credits."""
    lst = list_with_campaign
    lst.credits_current = 100  # Not enough for vehicle (180) + crew (50) = 230
    lst.save()

    # Create vehicle fighter
    vehicle_fighter = make_content_fighter(
        type="Ridgehauler",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=180,
    )

    # Create crew fighter
    crew_fighter = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    # Create vehicle equipment
    vehicle_equipment = make_equipment("Ridgehauler", cost="180", category="Vehicles")

    # Call the handler - should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        handle_vehicle_purchase(
            user=user,
            lst=lst,
            vehicle_equipment=vehicle_equipment,
            vehicle_fighter=vehicle_fighter,
            crew_fighter=crew_fighter,
            crew_name="Test Crew",
            is_stash=False,
        )

    assert "Insufficient credits" in str(exc_info.value)

    # Verify no objects created
    assert ListFighter.objects.filter(name="Test Crew").count() == 0
    assert (
        ListFighterEquipmentAssignment.objects.filter(
            content_equipment=vehicle_equipment
        ).count()
        == 0
    )

    # Verify no additional actions created (only the initial CREATE action)
    assert ListAction.objects.count() == 1
    assert ListAction.objects.first().action_type == ListActionType.CREATE

    # Verify credits unchanged (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 100


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_vehicle_purchase_correct_before_values(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test that before values are captured correctly in ListActions."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.stash_current = 200
    lst.save()

    # Create vehicle fighter
    vehicle_fighter = make_content_fighter(
        type="Ridgehauler",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=180,
    )

    # Create crew fighter
    crew_fighter = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    # Create vehicle equipment
    vehicle_equipment = make_equipment("Ridgehauler", cost="180", category="Vehicles")

    # Call the handler
    result = handle_vehicle_purchase(
        user=user,
        lst=lst,
        vehicle_equipment=vehicle_equipment,
        vehicle_fighter=vehicle_fighter,
        crew_fighter=crew_fighter,
        crew_name="Test Crew",
        is_stash=False,
    )

    if feature_flag_enabled:
        # Verify before values in both actions
        assert result.crew_list_action.rating_before == 500
        assert result.crew_list_action.stash_before == 200
        assert result.crew_list_action.credits_before == 1000

        assert result.vehicle_list_action.rating_before == 500
        assert result.vehicle_list_action.stash_before == 200
        assert result.vehicle_list_action.credits_before == 1000
    else:
        assert result.crew_list_action is None
        assert result.vehicle_list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_vehicle_purchase_transaction_rollback(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    make_equipment,
    monkeypatch,
    settings,
    feature_flag_enabled,
):
    """Test that transaction rolls back on error."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    # Create vehicle fighter
    vehicle_fighter = make_content_fighter(
        type="Ridgehauler",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=180,
    )

    # Create crew fighter
    crew_fighter = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    # Create vehicle equipment
    vehicle_equipment = make_equipment("Ridgehauler", cost="180", category="Vehicles")

    # Count initial objects
    initial_fighter_count = ListFighter.objects.count()
    initial_assignment_count = ListFighterEquipmentAssignment.objects.count()
    initial_action_count = ListAction.objects.count()

    if feature_flag_enabled:
        # Monkeypatch create_action to raise an error after some operations
        original_create_action = lst.create_action

        def failing_create_action(*args, **kwargs):
            # Let the first action succeed, fail on the second
            if ListAction.objects.count() > initial_action_count:
                raise RuntimeError("Simulated error")
            return original_create_action(*args, **kwargs)

        monkeypatch.setattr(lst, "create_action", failing_create_action)

        # Call the handler - should raise error and rollback
        with pytest.raises(RuntimeError):
            handle_vehicle_purchase(
                user=user,
                lst=lst,
                vehicle_equipment=vehicle_equipment,
                vehicle_fighter=vehicle_fighter,
                crew_fighter=crew_fighter,
                crew_name="Test Crew",
                is_stash=False,
            )

        # Verify transaction rolled back - no new objects created
        assert ListFighter.objects.count() == initial_fighter_count
        assert (
            ListFighterEquipmentAssignment.objects.count() == initial_assignment_count
        )
        assert ListAction.objects.count() == initial_action_count

        # Verify credits unchanged
        # Refresh needed here because: handler modified the object (spend_credits), then transaction
        # failed and rolled back. DB is correct, but Python object still has modified value.
        # In the running app, this is fine - the modified object is discarded after the view returns.
        lst.refresh_from_db()
        assert lst.credits_current == 1000
    else:
        # When feature flag is disabled, we can't test transaction rollback via create_action
        # since no actions are created. Instead, just verify the purchase completes successfully.
        handle_vehicle_purchase(
            user=user,
            lst=lst,
            vehicle_equipment=vehicle_equipment,
            vehicle_fighter=vehicle_fighter,
            crew_fighter=crew_fighter,
            crew_name="Test Crew",
            is_stash=False,
        )

        # Verify objects were created successfully
        assert ListFighter.objects.count() == initial_fighter_count + 1
        assert (
            ListFighterEquipmentAssignment.objects.count()
            == initial_assignment_count + 1
        )
        assert (
            ListAction.objects.count() == initial_action_count
        )  # No new actions when flag disabled

        # Verify credits spent
        assert lst.credits_current == 770
