"""
Tests for fighter lifecycle handlers (kill and resurrect).

These tests directly test the handler functions in gyrinx.core.handlers.fighter,
ensuring that business logic works correctly without involving HTTP machinery.
"""

import pytest

from gyrinx.core.handlers.fighter.kill import handle_fighter_kill
from gyrinx.core.handlers.fighter.resurrect import handle_fighter_resurrect
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.list import ListFighter


# ===== Kill Handler Tests =====


@pytest.mark.django_db
def test_handle_fighter_kill_basic(user, list_with_campaign, content_fighter, settings):
    """Test killing a fighter creates correct actions and reduces rating."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    fighter_cost_before = fighter.cost_int()
    rating_before = lst.rating_current

    result = handle_fighter_kill(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify result
    assert result.fighter == fighter
    assert result.fighter_cost_before == fighter_cost_before
    assert result.equipment_count == 0

    # Verify ListAction created
    assert result.list_action is not None
    assert result.list_action.action_type == ListActionType.UPDATE_FIGHTER
    assert result.list_action.rating_delta == -fighter_cost_before
    assert result.list_action.stash_delta == 0
    assert result.list_action.credits_delta == 0
    assert result.list_action.rating_before == rating_before

    # Verify fighter updated
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD
    assert fighter.cost_override == 0

    # Verify CampaignAction created
    assert result.campaign_action is not None
    assert "was killed" in result.campaign_action.description


@pytest.mark.django_db
def test_handle_fighter_kill_propagates_to_fighter_rating_current(
    user, list_with_campaign, content_fighter, settings
):
    """Test that killing a fighter propagates negative delta to fighter.rating_current."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Set initial rating_current manually
    fighter.rating_current = 100
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current
    fighter_cost_before = fighter.cost_int()

    result = handle_fighter_kill(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify rating_delta is negative
    assert result.list_action.rating_delta == -fighter_cost_before

    # Verify fighter.rating_current propagated (reduced to 0)
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating - fighter_cost_before


@pytest.mark.django_db
def test_handle_fighter_kill_with_equipment(
    user, list_with_campaign, content_fighter, make_equipment, settings
):
    """Test killing a fighter with equipment transfers equipment to stash."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    # Create stash fighter
    from gyrinx.models import FighterCategoryChoices

    # We need the make_content_fighter fixture, but we'll create a simple stash manually
    stash_type = content_fighter.__class__.objects.create(
        house=content_fighter.house,
        type="Stash",
        category=FighterCategoryChoices.CREW,
        base_cost=0,
        is_stash=True,
    )
    stash_fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_type,
        list=lst,
        owner=user,
    )

    # Create fighter with equipment
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    equipment = make_equipment("Test Weapon", cost="50")
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    result = handle_fighter_kill(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify equipment transferred
    assert result.equipment_count == 1

    # Verify equipment is now on stash
    assert stash_fighter.listfighterequipmentassignment_set.count() == 1

    # Verify description mentions equipment transfer
    assert "equipment transferred to stash" in result.description.lower()


# ===== Resurrect Handler Tests =====


@pytest.mark.django_db
def test_handle_fighter_resurrect_basic(
    user, list_with_campaign, content_fighter, settings
):
    """Test resurrecting a dead fighter creates correct actions and restores rating."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    # Create a dead fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
        cost_override=0,  # Dead fighters have cost 0
    )

    # Calculate what the restored cost will be
    restored_cost = fighter._base_cost_before_override()
    rating_before = lst.rating_current

    result = handle_fighter_resurrect(
        user=user,
        fighter=fighter,
    )

    # Verify result
    assert result.fighter == fighter
    assert result.restored_cost == restored_cost

    # Verify ListAction created
    assert result.list_action is not None
    assert result.list_action.action_type == ListActionType.UPDATE_FIGHTER
    assert result.list_action.rating_delta == restored_cost
    assert result.list_action.stash_delta == 0
    assert result.list_action.credits_delta == 0
    assert result.list_action.rating_before == rating_before

    # Verify fighter updated
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.ACTIVE
    assert fighter.cost_override is None
    assert fighter.cost_int() == restored_cost

    # Verify CampaignAction created
    assert result.campaign_action is not None
    assert "resurrection" in result.campaign_action.description.lower()


@pytest.mark.django_db
def test_handle_fighter_resurrect_propagates_to_fighter_rating_current(
    user, list_with_campaign, content_fighter, settings
):
    """Test that resurrecting a fighter propagates positive delta to fighter.rating_current."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    # Create a dead fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
        cost_override=0,
    )

    # Dead fighter starts with rating_current = 0
    fighter.rating_current = 0
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current
    restored_cost = fighter._base_cost_before_override()

    result = handle_fighter_resurrect(
        user=user,
        fighter=fighter,
    )

    # Verify rating_delta is positive
    assert result.list_action.rating_delta == restored_cost

    # Verify fighter.rating_current propagated (increased from 0 to restored_cost)
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating + restored_cost


@pytest.mark.django_db
def test_handle_fighter_resurrect_validates_campaign_mode(
    user, make_list, content_fighter
):
    """Test resurrection only works in campaign mode."""
    lst = make_list("Test List")  # List building mode

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
        cost_override=0,
    )

    with pytest.raises(ValueError, match="campaign mode"):
        handle_fighter_resurrect(
            user=user,
            fighter=fighter,
        )


@pytest.mark.django_db
def test_handle_fighter_resurrect_validates_dead_state(
    user, list_with_campaign, content_fighter
):
    """Test resurrection only works on dead fighters."""
    lst = list_with_campaign

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.ACTIVE,  # Not dead
    )

    with pytest.raises(ValueError, match="dead fighters"):
        handle_fighter_resurrect(
            user=user,
            fighter=fighter,
        )


@pytest.mark.django_db
def test_handle_fighter_resurrect_validates_not_stash(
    user, list_with_campaign, make_content_fighter, content_house
):
    """Test resurrection rejects stash fighters."""
    lst = list_with_campaign

    from gyrinx.models import FighterCategoryChoices

    stash_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )

    stash_fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_type,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
        cost_override=0,
    )

    with pytest.raises(ValueError, match="stash"):
        handle_fighter_resurrect(
            user=user,
            fighter=stash_fighter,
        )
