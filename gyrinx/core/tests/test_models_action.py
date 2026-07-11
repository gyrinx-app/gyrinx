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


# Test for protection against negative values


@pytest.mark.django_db
def test_list_write_prevents_negative_rating_and_stash(user, make_list, settings):
    """The list-level cache writer clamps rating/stash at zero.

    Applying negative movement (e.g. removing fighters or equipment) clamps
    the cached values to 0 rather than going negative. The writer is the
    propagation layer; create_action only records and never mutates.
    """
    from gyrinx.core.cost.propagation import propagate_to_list

    lst = make_list("Test List")

    # Set initial values
    lst.rating_current = 50
    lst.stash_current = 30
    lst.credits_current = 100
    lst.save()

    # Create initial action to establish baseline
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        description="Initial state",
        rating_delta=0,
        stash_delta=0,
        credits_delta=0,
    )

    # Apply movement that would make values go negative without the clamp
    # rating: 50 - 100 = -50 (clamped to 0); stash: 30 - 50 = -20 (clamped)
    propagate_to_list(lst, rating_delta=-100, stash_delta=-50)
    action = lst.create_action(
        user=user,
        action_type=ListActionType.REMOVE_FIGHTER,
        description="Remove expensive fighter",
        rating_delta=-100,
        stash_delta=-50,
        credits_delta=0,
        rating_before=50,
        stash_before=30,
        credits_before=100,
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

    # Recording alone never moves the caches: a second record with large
    # negative deltas leaves the (already clamped) values untouched.
    lst.create_action(
        user=user,
        action_type=ListActionType.REMOVE_FIGHTER,
        description="Record only",
        rating_delta=-999,
        stash_delta=-999,
        credits_delta=-999,
    )
    lst.refresh_from_db()
    assert lst.rating_current == 0
    assert lst.stash_current == 0
    assert lst.credits_current == 100
