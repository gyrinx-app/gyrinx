import pytest

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)

pylist = list

# Basic Object Creation Tests


@pytest.mark.django_db
def test_create_list_action_basic(user, make_list):
    """Test creating a ListAction with minimal required fields."""
    lst = make_list("Test List")

    # ActionType has no choices yet, so we'll use an empty string
    action = ListAction.objects.create(
        list=lst,
        action_type="",
        owner=user,
        applied=True,
    )

    assert action.list == lst
    assert action.action_type == ""
    assert action.rating_delta == 0
    assert action.rating_before == 0
    assert action.owner == user


@pytest.mark.django_db
def test_create_list_action_with_optional_fields(user, make_list):
    """Test creating a ListAction with optional fields populated."""
    lst = make_list("Test List")

    action = ListAction.objects.create(
        list=lst,
        action_type="",
        owner=user,
        applied=True,
        subject_app="core",
        subject_type="ListFighter",
        subject_id="12345678-1234-1234-1234-123456789012",
        description="Test action description",
    )

    assert action.subject_app == "core"
    assert action.subject_type == "ListFighter"
    assert str(action.subject_id) == "12345678-1234-1234-1234-123456789012"
    assert action.description == "Test action description"


@pytest.mark.django_db
def test_create_list_action_with_credit_tracking(user, make_list):
    """Test creating a ListAction with credit tracking fields."""
    lst = make_list("Test List")

    action = ListAction.objects.create(
        list=lst,
        action_type="",
        owner=user,
        applied=True,
        rating_before=100,
        rating_delta=50,
        credits_before=200,
        credits_delta=-50,
    )

    assert action.rating_delta == 50
    assert action.rating_before == 100
    assert action.credits_before == 200
    assert action.credits_delta == -50


@pytest.mark.django_db
def test_rating_after_calculation(user, make_list):
    """Test that rating_after property calculates correctly."""
    lst = make_list("Test List")

    action = ListAction.objects.create(
        list=lst,
        action_type=ListActionType.ADD_FIGHTER,
        owner=user,
        applied=True,
        rating_before=200,
        rating_delta=75,
        credits_before=200,
        credits_delta=-75,
    )

    assert action.rating_after == 275
    assert action.credits_after == 125

    # Test with negative delta
    action2 = ListAction.objects.create(
        list=lst,
        action_type=ListActionType.ADD_FIGHTER,
        owner=user,
        applied=True,
        rating_before=200,
        rating_delta=-50,
        credits_before=200,
        credits_delta=50,
    )

    assert action2.rating_after == 150
    assert action2.credits_after == 250


@pytest.mark.django_db
def test_stash_after_calculation(user, make_list):
    """Test that stash_after property calculates correctly."""
    lst = make_list("Test List")

    action = ListAction.objects.create(
        list=lst,
        action_type=ListActionType.ADD_FIGHTER,
        owner=user,
        applied=True,
        stash_before=100,
        stash_delta=50,
        credits_before=200,
        credits_delta=-50,
    )

    assert action.stash_after == 150
    assert action.credits_after == 150

    # Test with negative delta
    action2 = ListAction.objects.create(
        list=lst,
        action_type=ListActionType.ADD_FIGHTER,
        owner=user,
        applied=True,
        stash_before=100,
        stash_delta=-50,
        credits_before=200,
        credits_delta=50,
    )

    assert action2.stash_after == 50
    assert action2.credits_after == 250


@pytest.mark.django_db
def test_multi_delta_calculation(user, make_list):
    """Test that multi-delta properties calculate correctly."""
    lst = make_list("Test List")

    action = ListAction.objects.create(
        list=lst,
        action_type=ListActionType.ADD_FIGHTER,
        owner=user,
        applied=True,
        stash_before=100,
        stash_delta=50,
        rating_before=200,
        rating_delta=75,
        credits_before=200,
        credits_delta=-75,
    )

    assert action.stash_after == 150
    assert action.rating_after == 275
    assert action.credits_after == 125

    # Test with negative delta
    action2 = ListAction.objects.create(
        list=lst,
        action_type=ListActionType.ADD_FIGHTER,
        owner=user,
        applied=True,
        stash_delta=-50,
        stash_before=100,
        rating_delta=-75,
        rating_before=200,
        credits_before=200,
        credits_delta=125,
    )

    assert action2.stash_after == 50
    assert action2.rating_after == 125
    assert action2.credits_after == 325


# Deletion Behavior Tests


@pytest.mark.django_db
def test_cascade_delete_when_list_deleted(user, make_list):
    """Test that ListAction is deleted when parent List is deleted (CASCADE)."""
    lst = make_list("Test List")

    action = ListAction.objects.create(
        list=lst,
        action_type=ListActionType.CREATE,
        owner=user,
        applied=True,
    )

    action_id = action.id

    # Delete the list
    lst.delete()

    # Verify the action was also deleted
    assert not ListAction.objects.filter(id=action_id).exists()


@pytest.mark.django_db
def test_set_null_when_list_fighter_deleted(user, make_list, make_list_fighter):
    """Test that ListAction remains when referenced ListFighter is deleted (SET_NULL)."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    action = ListAction.objects.create(
        list=lst,
        action_type=ListActionType.ADD_FIGHTER,
        owner=user,
        applied=True,
        list_fighter=fighter,
    )

    action_id = action.id
    fighter_id = fighter.id

    # Delete the fighter
    fighter.delete()

    # Verify the action still exists (SET_NULL means no cascading delete)
    assert ListAction.objects.filter(id=action_id).exists()

    # Verify the fighter is deleted
    assert not ListFighter.objects.filter(id=fighter_id).exists()


@pytest.mark.django_db
def test_set_null_when_assignment_deleted(
    user, content_house, content_fighter, make_list, make_list_fighter, make_equipment
):
    """Test that ListAction remains when referenced ListFighterEquipmentAssignment is deleted (SET_NULL)."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")
    equipment = make_equipment("Test Equipment", cost=10)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    action = ListAction.objects.create(
        list=lst,
        action_type=ListActionType.ADD_EQUIPMENT,
        owner=user,
        applied=True,
        list_fighter_equipment_assignment=assignment,
    )

    action_id = action.id
    assignment_id = assignment.id

    # Delete the assignment
    assignment.delete()

    # Verify the action still exists
    assert ListAction.objects.filter(id=action_id).exists()

    # Verify the assignment is deleted
    assert not ListFighterEquipmentAssignment.objects.filter(id=assignment_id).exists()


# latest_for_list Method Tests


@pytest.mark.django_db
def test_latest_for_list_single_action(user, make_list):
    """Test getting the latest action when only one exists."""
    lst = make_list("Test List")

    action = ListAction.objects.create(
        list=lst,
        action_type="",
        owner=user,
        applied=True,
    )

    latest = ListAction.objects.latest_for_list(lst.id)

    assert latest == action


@pytest.mark.django_db
def test_latest_for_list_multiple_actions(user, make_list):
    """Test getting the most recent action when multiple exist."""
    lst = make_list("Test List")

    # Create multiple actions
    ListAction.objects.create(
        list=lst,
        action_type="",
        owner=user,
        applied=True,
    )

    ListAction.objects.create(
        list=lst,
        action_type="",
        owner=user,
        applied=True,
    )

    action3 = ListAction.objects.create(
        list=lst,
        action_type="",
        owner=user,
        applied=True,
    )

    latest = ListAction.objects.latest_for_list(lst.id)

    # Should return the most recently created action
    assert latest == action3


@pytest.mark.django_db
def test_latest_for_list_no_actions(user, make_list):
    """Test that None is returned when list has no actions."""
    # Create list without initial action to test edge case
    lst = make_list("Test List", create_initial_action=False)

    latest = ListAction.objects.latest_for_list(lst.id)

    assert latest is None


@pytest.mark.django_db
def test_latest_for_list_filters_by_list(user, make_list):
    """Test that actions from other lists are not returned."""
    lst1 = make_list("Test List 1")
    lst2 = make_list("Test List 2")

    # Create actions for list 1
    action1 = ListAction.objects.create(
        list=lst1,
        action_type=ListActionType.CREATE,
        owner=user,
        applied=True,
    )

    # Create action for list 2
    action2 = ListAction.objects.create(
        list=lst2,
        action_type="",
        owner=user,
        applied=True,
    )

    # Get latest for list 1
    latest1 = ListAction.objects.latest_for_list(lst1.id)
    assert latest1 == action1

    # Get latest for list 2
    latest2 = ListAction.objects.latest_for_list(lst2.id)
    assert latest2 == action2


# List Prefetch Tests


@pytest.mark.django_db
def test_list_with_related_data_prefetch_latest_action(user, make_list):
    """Test that List.with_related_data() prefetches latest_action correctly."""
    # Create lists with multiple actions
    lst1 = make_list("Test List 1")
    lst2 = make_list("Test List 2")

    # Create actions for list 1 (oldest to newest)
    ListAction.objects.create(
        list=lst1,
        action_type=ListActionType.CREATE,
        owner=user,
        applied=True,
        rating_delta=10,
    )
    ListAction.objects.create(
        list=lst1,
        action_type=ListActionType.ADD_FIGHTER,
        owner=user,
        applied=True,
        rating_delta=20,
    )
    action1_3 = ListAction.objects.create(
        list=lst1,
        action_type=ListActionType.ADD_EQUIPMENT,
        owner=user,
        applied=True,
        rating_delta=30,
    )

    # Create actions for list 2
    action2_1 = ListAction.objects.create(
        list=lst2,
        action_type=ListActionType.CREATE,
        owner=user,
        applied=True,
        rating_delta=100,
    )

    # Fetch lists using with_related_data()
    lists = List.objects.filter(id__in=[lst1.id, lst2.id]).with_related_data().all()

    # Verify we got both lists
    assert len(lists) == 2

    # Find the specific lists
    fetched_lst1 = next(lst for lst in lists if lst.id == lst1.id)
    fetched_lst2 = next(lst for lst in lists if lst.id == lst2.id)

    # Verify latest_action is accessible and correct for list 1
    assert hasattr(fetched_lst1, "latest_actions")
    assert fetched_lst1.latest_action is not None
    assert fetched_lst1.latest_action.id == action1_3.id

    # Verify latest_actions is accessible and correct for list 2
    assert hasattr(fetched_lst2, "latest_actions")
    assert fetched_lst2.latest_action is not None
    assert fetched_lst2.latest_action.id == action2_1.id


# List check_wealth_sync Tests


@pytest.mark.django_db
def test_check_wealth_sync_no_latest_action(user, make_list):
    """Test that check_wealth_sync does nothing when there is no latest_action."""
    from unittest.mock import patch

    # Create list without initial action to test edge case
    lst = make_list("Test List", create_initial_action=False)

    # No latest_action, so check_wealth_sync should do nothing
    with patch("gyrinx.core.models.list.track") as mock_track:
        lst.check_wealth_sync(wealth_calculated=1000)
        # track should not be called
        mock_track.assert_not_called()


@pytest.mark.django_db
def test_check_wealth_sync_in_sync(user, make_list):
    """Test that check_wealth_sync does not call track when wealth is in sync."""
    from unittest.mock import patch

    lst = make_list("Test List")

    # Create an action
    ListAction.objects.create(
        list=lst,
        action_type=ListActionType.CREATE,
        owner=user,
        applied=True,
        rating_before=0,
        rating_delta=500,  # Spent 500 credits on rating
        credits_before=1000,
        credits_delta=-500,  # Spent 500 credits
    )

    # Fetch the list with latest_action populated
    lst = List.objects.filter(id=lst.id).with_related_data().first()

    # Set rating_current and credits_current to match the action
    # After action: rating_after = 0 + 500 = 500, credits_after = 1000 - 500 = 500
    lst.rating_current = 500
    lst.credits_current = 500
    lst.save()

    # Calculated cost = rating_current + credits_current = 500 + 500 = 1000
    # Action total = rating_after + credits_after = 500 + 500 = 1000
    # Both match, so track should not be called
    with patch("gyrinx.core.models.list.track") as mock_track:
        lst.check_wealth_sync(wealth_calculated=1000)
        mock_track.assert_not_called()


@pytest.mark.django_db
def test_check_wealth_sync_out_of_sync_current(user, make_list):
    """Test that check_wealth_sync calls track when rating_current is out of sync."""
    from unittest.mock import patch

    lst = make_list("Test List")

    # Create an action
    ListAction.objects.create(
        list=lst,
        action_type=ListActionType.CREATE,
        owner=user,
        applied=True,
        rating_before=0,
        rating_delta=500,
        credits_before=1000,
        credits_delta=-500,
    )

    # Fetch the list with latest_action populated
    lst = List.objects.filter(id=lst.id).with_related_data().first()

    # Set rating_current incorrectly
    lst.rating_current = 400
    lst.credits_current = 500
    lst.save()

    # Calculated cost = 1000
    # rating_current + credits_current = 400 + 500 = 900 (out of sync by 100)
    # rating_after + credits_after = 500 + 500 = 1000 (in sync)
    with patch("gyrinx.core.models.list.track") as mock_track:
        lst.check_wealth_sync(wealth_calculated=1000)
        mock_track.assert_called_once()
        call_args = mock_track.call_args[1]
        assert call_args["list_id"] == str(lst.id)
        assert call_args["wealth_calculated"] == 1000
        assert call_args["rating_current"] == 400
        assert call_args["stash_current"] == 0
        assert call_args["credits_current"] == 500
        # Note: we don't really care about the action here, but we can check them anyway
        assert call_args["latest_action_wealth_after"] == 1000
        assert call_args["latest_action_rating_after"] == 500
        assert call_args["latest_action_stash_after"] == 0
        assert call_args["latest_action_credits_after"] == 500


@pytest.mark.django_db
def test_check_wealth_sync_out_of_sync_action(user, make_list):
    """Test that check_wealth_sync calls track when latest_action is out of sync."""
    from unittest.mock import patch

    lst = make_list("Test List")

    # Create an action with incorrect values
    ListAction.objects.create(
        list=lst,
        action_type=ListActionType.CREATE,
        owner=user,
        applied=True,
        rating_before=100,
        rating_delta=500,
        credits_before=1000,
        credits_delta=-500,
    )

    # Fetch the list with latest_action populated
    lst = List.objects.filter(id=lst.id).with_related_data().first()

    # Set rating_current and credits_current correctly
    lst.rating_current = 500
    lst.credits_current = 500
    lst.save()

    with patch("gyrinx.core.models.list.track") as mock_track:
        lst.check_wealth_sync(wealth_calculated=1000)
        mock_track.assert_called_once()
        call_args = mock_track.call_args[1]
        assert call_args["list_id"] == str(lst.id)
        assert call_args["wealth_calculated"] == 1000
        assert call_args["rating_current"] == 500
        assert call_args["stash_current"] == 0
        assert call_args["credits_current"] == 500
        assert call_args["latest_action_wealth_after"] == 1100
        assert call_args["latest_action_rating_after"] == 600
        assert call_args["latest_action_stash_after"] == 0
        assert call_args["latest_action_credits_after"] == 500


# Test for protection against negative values


@pytest.mark.django_db
def test_create_action_prevents_negative_rating_and_stash(user, make_list, settings):
    """Test that create_action prevents rating_current and stash_current from going negative.

    When applying negative deltas (e.g., removing fighters or equipment), the values
    should be clamped to 0 rather than going negative.
    """
    # Enable feature flag for initial action creation
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = make_list("Test List")

    # Set initial values
    lst.rating_current = 50
    lst.stash_current = 30
    lst.credits_current = 100
    lst.save()

    # Create initial action to establish baseline
    lst.create_action(
        user=user,
        update_credits=True,
        action_type=ListActionType.UPDATE_FIGHTER,
        description="Initial state",
        rating_delta=0,
        stash_delta=0,
        credits_delta=0,
    )

    # Apply action with negative deltas that would make values go negative without the fix
    # rating: 50 - 100 = -50 (should be clamped to 0)
    # stash: 30 - 50 = -20 (should be clamped to 0)
    action = lst.create_action(
        user=user,
        update_credits=True,
        action_type=ListActionType.REMOVE_FIGHTER,
        description="Remove expensive fighter",
        rating_delta=-100,
        stash_delta=-50,
        credits_delta=0,
    )

    assert action is not None

    # Refresh from database to get updated values
    lst.refresh_from_db()

    # Verify that rating_current and stash_current are clamped to 0, not negative
    assert lst.rating_current == 0, (
        "rating_current should be clamped to 0, not negative"
    )
    assert lst.stash_current == 0, "stash_current should be clamped to 0, not negative"
    assert lst.credits_current == 100, "credits_current should remain unchanged"

    # Verify the action records the correct before/delta values
    assert action.rating_before == 50
    assert action.rating_delta == -100
    assert action.stash_before == 30
    assert action.stash_delta == -50
    assert action.credits_before == 100
    assert action.credits_delta == 0

    # The after values should reflect the clamped results
    # Note: The action.rating_after is a calculated property (rating_before + rating_delta)
    # which would be -50, but the actual list.rating_current is clamped to 0
    assert action.rating_after == -50, (
        "Action's calculated rating_after can be negative"
    )
    assert action.stash_after == -20, "Action's calculated stash_after can be negative"
