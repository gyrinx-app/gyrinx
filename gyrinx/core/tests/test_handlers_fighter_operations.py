"""
Tests for fighter operation handlers.

These tests directly test the handle_fighter_hire function in
gyrinx.core.handlers.fighter.hire_clone, ensuring that business logic works
correctly without involving HTTP machinery.
"""

import pytest
from django.core.exceptions import ValidationError

from gyrinx.core.handlers.fighter import (
    FighterCloneParams,
    handle_fighter_clone,
    handle_fighter_hire,
)
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListFighter
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_hire_campaign_mode(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test hiring a fighter in campaign mode creates actions and spends credits."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.save()

    fighter_cost = content_fighter.cost_for_house(lst.content_house)

    # Create fighter instance (not saved yet)
    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Call the handler
    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify result
    assert result.fighter_cost == fighter_cost
    assert result.fighter == fighter
    assert f"Hired Test Fighter ({fighter_cost}¢)" in result.description

    # Verify fighter was saved
    assert result.fighter.id is not None
    assert ListFighter.objects.filter(id=result.fighter.id).exists()

    # Verify ListAction created
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.ADD_FIGHTER
        assert result.list_action.rating_delta == fighter_cost
        assert result.list_action.stash_delta == 0
        assert result.list_action.credits_delta == -fighter_cost
        assert result.list_action.rating_before == 500
        assert result.list_action.credits_before == 1000
    else:
        assert result.list_action is None

    # Verify CampaignAction created (always created in campaign mode)
    assert result.campaign_action is not None
    assert f"Hired Test Fighter ({fighter_cost}¢)" in result.campaign_action.description

    # Verify credits spent (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 1000 - fighter_cost


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_hire_list_building_mode(
    user, make_list, content_fighter, content_house, settings, feature_flag_enabled
):
    """Test hiring a fighter in list building mode (no credits)."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    fighter_cost = content_fighter.cost_for_house(content_house)

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify result
    assert result.fighter_cost == fighter_cost
    assert result.campaign_action is None  # No campaign mode

    # Verify ListAction created with no credit delta
    if feature_flag_enabled:
        assert result.list_action.credits_delta == 0
        assert result.list_action.rating_delta == fighter_cost
    else:
        assert result.list_action is None

    # Verify credits unchanged (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 0


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_hire_stash_fighter(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    settings,
    feature_flag_enabled,
):
    """Test hiring a stash fighter affects stash, not rating."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.stash_current = 100
    lst.rating_current = 500
    lst.save()

    # Create a stash fighter type
    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_type,
        name="Stash",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify stash delta, not rating delta
    if feature_flag_enabled:
        assert result.list_action.stash_delta == result.fighter_cost
        assert result.list_action.rating_delta == 0
        assert result.list_action.credits_delta == -result.fighter_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
def test_handle_fighter_hire_insufficient_credits(
    user, list_with_campaign, content_fighter
):
    """Test fighter hire fails with insufficient credits."""
    lst = list_with_campaign
    lst.credits_current = 25  # Not enough for 100 credit fighter
    lst.save()

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Should raise ValidationError due to insufficient credits
    with pytest.raises(ValidationError, match="Insufficient credits"):
        handle_fighter_hire(
            user=user,
            lst=lst,
            fighter=fighter,
        )

    # Verify no new actions created (only the initial CREATE action exists)
    assert ListAction.objects.count() == 1  # Only the initial CREATE action
    assert ListAction.objects.first().action_type == ListActionType.CREATE
    assert CampaignAction.objects.count() == 0

    # Verify fighter was not saved
    assert not ListFighter.objects.filter(name="Test Fighter").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_hire_correct_before_values(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test that before values are captured correctly in ListAction."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.stash_current = 200
    lst.save()

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify before values match original list state
    if feature_flag_enabled:
        assert result.list_action.rating_before == 500
        assert result.list_action.stash_before == 200
        assert result.list_action.credits_before == 1000
    else:
        assert result.list_action is None


@pytest.mark.django_db
def test_handle_fighter_hire_transaction_rollback(
    user, list_with_campaign, content_fighter, monkeypatch
):
    """Test that transaction rolls back on error."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Count initial objects
    initial_fighter_count = ListFighter.objects.count()
    initial_action_count = ListAction.objects.count()
    initial_campaign_action_count = CampaignAction.objects.count()

    # Monkeypatch create_action to raise an error
    def failing_create_action(*args, **kwargs):
        raise RuntimeError("Simulated error")

    monkeypatch.setattr(lst, "create_action", failing_create_action)

    # Call the handler - should raise error and rollback
    with pytest.raises(RuntimeError):
        handle_fighter_hire(
            user=user,
            lst=lst,
            fighter=fighter,
        )

    # Verify transaction rolled back - no new objects created
    assert ListFighter.objects.count() == initial_fighter_count
    assert ListAction.objects.count() == initial_action_count
    assert CampaignAction.objects.count() == initial_campaign_action_count

    # Verify credits unchanged
    # Refresh needed here because: handler modified the object (spend_credits), then transaction
    # failed and rolled back. DB is correct, but Python object still has modified value.
    # In the running app, this is fine - the modified object is discarded after the view returns.
    lst.refresh_from_db()
    assert lst.credits_current == 1000


@pytest.mark.django_db
def test_handle_fighter_hire_campaign_action_created(
    user, list_with_campaign, content_fighter
):
    """Test that CampaignAction is created in campaign mode."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    fighter_cost = content_fighter.cost_for_house(lst.content_house)

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify CampaignAction details
    assert result.campaign_action is not None
    assert result.campaign_action.campaign == lst.campaign
    assert result.campaign_action.list == lst
    assert f"Hired Test Fighter ({fighter_cost}¢)" in result.campaign_action.description
    assert (
        f"Credits remaining: {lst.credits_current}¢" in result.campaign_action.outcome
    )


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_hire_description_format(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test that description is formatted correctly."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    fighter_cost = content_fighter.cost_for_house(lst.content_house)

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Specialized Fighter Name",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify description format includes name and cost
    expected_desc = f"Hired Specialized Fighter Name ({fighter_cost}¢)"
    assert result.description == expected_desc
    if feature_flag_enabled:
        assert result.list_action.description == expected_desc
    else:
        assert result.list_action is None
    assert expected_desc in result.campaign_action.description


# ===== Fighter Clone Tests =====


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_same_list_campaign_mode(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test cloning a fighter to the same list in campaign mode."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.save()

    # Create original fighter
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
    )
    fighter_cost = original_fighter.cost_int()

    # Call the handler (clone happens internally)
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=lst,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify result
    assert result.fighter.name == "Cloned Fighter"
    assert result.source_fighter == original_fighter
    assert result.fighter_cost == fighter_cost
    assert "Cloned Fighter" in result.description
    assert "Original Fighter" in result.description

    # Verify ListAction created on target list
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.ADD_FIGHTER
        assert result.list_action.rating_delta == fighter_cost
        assert result.list_action.stash_delta == 0
        assert result.list_action.credits_delta == -fighter_cost
        assert result.list_action.rating_before == 500
        assert result.list_action.credits_before == 1000
    else:
        assert result.list_action is None

    # Verify CampaignAction created (always created in campaign mode)
    assert result.campaign_action is not None
    assert "Cloned" in result.campaign_action.description

    # Verify credits spent
    assert lst.credits_current == 1000 - fighter_cost


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_different_list_campaign_mode(
    user, list_with_campaign, make_list, content_fighter, settings, feature_flag_enabled
):
    """Test cloning a fighter to a different list in campaign mode."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    source_list = list_with_campaign
    source_list.rating_current = 500
    source_list.credits_current = 1000
    source_list.save()

    # Create target list in same campaign
    target_list = make_list(
        "Target List",
        status=source_list.CAMPAIGN_MODE,
        campaign=source_list.campaign,
    )
    target_list.rating_current = 300
    target_list.credits_current = 800
    target_list.save()

    # Create original fighter on source list
    original_fighter = ListFighter.objects.create(
        list=source_list,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
    )
    fighter_cost = original_fighter.cost_int()

    # Call the handler (clone to target list happens internally)
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=target_list,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify action created on TARGET list only
    if feature_flag_enabled:
        assert result.list_action.list == target_list
        assert result.list_action.rating_before == 300
        assert result.list_action.credits_before == 800
    else:
        assert result.list_action is None

    # Verify target list credits spent
    assert target_list.credits_current == 800 - fighter_cost

    # Verify source list unchanged (no refresh needed)
    assert source_list.credits_current == 1000
    assert source_list.rating_current == 500


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_list_building_mode(
    user, make_list, content_fighter, content_house, settings, feature_flag_enabled
):
    """Test cloning a fighter in list building mode (no credits)."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create original fighter
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
    )
    fighter_cost = original_fighter.cost_int()

    # Call the handler (clone happens internally)
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=lst,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify result
    assert result.fighter_cost == fighter_cost
    assert result.campaign_action is None  # No campaign mode

    # Verify ListAction created with no credit delta
    if feature_flag_enabled:
        assert result.list_action.credits_delta == 0
        assert result.list_action.rating_delta == fighter_cost
    else:
        assert result.list_action is None

    # Verify credits unchanged
    assert lst.credits_current == 0


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_stash_fighter(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    settings,
    feature_flag_enabled,
):
    """Test cloning a stash fighter affects stash, not rating."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.stash_current = 100
    lst.rating_current = 500
    lst.save()

    # Create a stash fighter type
    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=50,
        is_stash=True,
    )

    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_type,
        name="Original Stash",
    )
    fighter_cost = original_fighter.cost_int()

    # Call the handler (clone happens internally)
    clone_params = FighterCloneParams(
        name="Cloned Stash",
        content_fighter=stash_fighter_type,
        target_list=lst,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify stash delta, not rating delta
    if feature_flag_enabled:
        assert result.list_action.stash_delta == fighter_cost
        assert result.list_action.rating_delta == 0
        assert result.list_action.credits_delta == -fighter_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_with_equipment(
    user,
    list_with_campaign,
    content_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test cloning a fighter with equipment includes equipment cost."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 2000
    lst.rating_current = 500
    lst.save()

    # Create original fighter with equipment
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
    )

    # Add equipment to the original fighter
    equipment = make_equipment(name="Test Weapon", cost="50")
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    ListFighterEquipmentAssignment.objects.create(
        list_fighter=original_fighter,
        content_equipment=equipment,
    )

    # Get total cost (fighter + equipment)
    total_cost = original_fighter.cost_int()

    # Call the handler (clone happens internally, equipment is cloned automatically)
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=lst,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify cost includes equipment
    assert result.fighter_cost == total_cost
    if feature_flag_enabled:
        assert result.list_action.rating_delta == total_cost
        assert result.list_action.credits_delta == -total_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
def test_handle_fighter_clone_insufficient_credits(
    user, list_with_campaign, content_fighter
):
    """Test fighter clone fails with insufficient credits."""
    lst = list_with_campaign
    lst.credits_current = 25  # Not enough
    lst.save()

    # Create original fighter
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
    )

    # Count initial actions and fighters before clone attempt
    initial_action_count = ListAction.objects.count()
    initial_campaign_action_count = CampaignAction.objects.count()
    initial_fighter_count = ListFighter.objects.count()

    # Should raise ValidationError due to insufficient credits
    # The clone should be rolled back by the transaction
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=lst,
    )
    with pytest.raises(ValidationError, match="Insufficient credits"):
        handle_fighter_clone(
            user=user,
            source_fighter=original_fighter,
            clone_params=clone_params,
        )

    # Verify no new actions or fighters created (clone was rolled back)
    assert ListAction.objects.count() == initial_action_count
    assert CampaignAction.objects.count() == initial_campaign_action_count
    assert ListFighter.objects.count() == initial_fighter_count


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_correct_before_values(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test that before values are captured correctly in ListAction."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.stash_current = 200
    lst.save()

    # Create original fighter
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
    )

    # Call the handler (clone happens internally)
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=lst,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify before values match original list state
    if feature_flag_enabled:
        assert result.list_action.rating_before == 500
        assert result.list_action.stash_before == 200
        assert result.list_action.credits_before == 1000
    else:
        assert result.list_action is None


@pytest.mark.django_db
def test_handle_fighter_clone_transaction_rollback(
    user, list_with_campaign, content_fighter, monkeypatch
):
    """Test that transaction rolls back on error."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    # Create original fighter
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
    )

    # Count initial objects
    initial_action_count = ListAction.objects.count()
    initial_campaign_action_count = CampaignAction.objects.count()
    initial_fighter_count = ListFighter.objects.count()
    initial_credits = lst.credits_current

    # Monkeypatch create_action to raise an error
    def failing_create_action(*args, **kwargs):
        raise RuntimeError("Simulated error")

    monkeypatch.setattr(lst, "create_action", failing_create_action)

    # Call the handler - should raise error and rollback
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=lst,
    )
    with pytest.raises(RuntimeError):
        handle_fighter_clone(
            user=user,
            source_fighter=original_fighter,
            clone_params=clone_params,
        )

    # Verify transaction rolled back - no new actions or fighters created
    assert ListAction.objects.count() == initial_action_count
    assert CampaignAction.objects.count() == initial_campaign_action_count
    assert ListFighter.objects.count() == initial_fighter_count

    # Verify credits unchanged (refresh needed for same reason as hire test)
    lst.refresh_from_db()
    assert lst.credits_current == initial_credits


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_description_format(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test that description is formatted correctly."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    # Create original fighter
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Source Fighter Name",
    )
    fighter_cost = original_fighter.cost_int()

    # Call the handler (clone happens internally)
    clone_params = FighterCloneParams(
        name="Target Fighter Name",
        content_fighter=content_fighter,
        target_list=lst,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify description format includes both names and cost
    expected_desc = (
        f"Cloned Target Fighter Name from Source Fighter Name ({fighter_cost}¢)"
    )
    assert result.description == expected_desc
    if feature_flag_enabled:
        assert result.list_action.description == expected_desc
    else:
        assert result.list_action is None
    assert expected_desc in result.campaign_action.description


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_with_category_override(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test cloning a fighter with category_override preserves the override."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    # Create original fighter with category override
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
        category_override=FighterCategoryChoices.CHAMPION,
    )

    # Call the handler with category override
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=lst,
        category_override=FighterCategoryChoices.CHAMPION,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify category override was cloned
    assert result.fighter.category_override == FighterCategoryChoices.CHAMPION
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.ADD_FIGHTER
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_clear_category_override(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test cloning a fighter can clear category_override (unchecked checkbox)."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    # Create original fighter with category override
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
        category_override=FighterCategoryChoices.CHAMPION,
    )

    # Call the handler without category override (checkbox unchecked = None)
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=lst,
        category_override=None,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify category override was cleared
    assert result.fighter.category_override is None
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.ADD_FIGHTER
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_clone_no_category_override(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test cloning a fighter without category_override works normally."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    # Create original fighter WITHOUT category override
    original_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Original Fighter",
    )

    # Call the handler without providing category_override
    clone_params = FighterCloneParams(
        name="Cloned Fighter",
        content_fighter=content_fighter,
        target_list=lst,
    )
    result = handle_fighter_clone(
        user=user,
        source_fighter=original_fighter,
        clone_params=clone_params,
    )

    # Verify no category override on cloned fighter
    assert result.fighter.category_override is None
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.ADD_FIGHTER
    else:
        assert result.list_action is None


# ===== Rating Current Initialization Tests =====


@pytest.mark.django_db
def test_handle_fighter_hire_initializes_rating_current(
    user, list_with_campaign, content_fighter, settings
):
    """Test that hiring a fighter initializes rating_current to cost."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    result = handle_fighter_hire(user=user, lst=lst, fighter=fighter)

    # Verify rating_current initialized
    fighter.refresh_from_db()
    assert fighter.rating_current == result.fighter_cost
    assert fighter.rating_current == fighter.cost_int()


@pytest.mark.django_db
def test_handle_fighter_clone_initializes_rating_current(
    user, list_with_campaign, content_fighter, settings
):
    """Test that cloning a fighter initializes rating_current on clone."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    # Create source fighter
    source = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Source",
    )

    clone_params = FighterCloneParams(
        name="Clone",
        content_fighter=content_fighter,
        target_list=lst,
    )

    result = handle_fighter_clone(
        user=user,
        source_fighter=source,
        clone_params=clone_params,
    )

    # Verify rating_current initialized
    clone = result.fighter
    clone.refresh_from_db()
    assert clone.rating_current == result.fighter_cost
    assert clone.rating_current == clone.cost_int()
