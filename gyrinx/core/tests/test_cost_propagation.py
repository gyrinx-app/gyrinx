"""Tests for cost propagation functions."""

import pytest

from gyrinx.core.cost.propagation import (
    TransactDelta,
    propagate_from_assignment,
    propagate_from_fighter,
)
from gyrinx.core.cost.routing import is_stash_linked
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment


@pytest.mark.django_db
def test_transact_delta_properties(make_list):
    """Test TransactDelta dataclass properties."""
    lst = make_list("Test List")

    # Positive delta
    delta = TransactDelta(old_rating=100, new_rating=150, list=lst)
    assert delta.delta == 50
    assert delta.has_change is True

    # Negative delta
    delta = TransactDelta(old_rating=150, new_rating=100, list=lst)
    assert delta.delta == -50
    assert delta.has_change is True

    # No change
    delta = TransactDelta(old_rating=100, new_rating=100, list=lst)
    assert delta.delta == 0
    assert delta.has_change is False


@pytest.mark.django_db
def test_propagate_from_assignment_basic(
    user, make_list, content_fighter, make_equipment
):
    """Test basic assignment propagation updates assignment and fighter, but NOT list."""
    lst = make_list("Test List")
    lst.rating_current = 0
    lst.stash_current = 0
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=0,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=0,
        dirty=True,
    )

    # Propagate a cost increase
    delta = TransactDelta(old_rating=0, new_rating=50, list=lst)
    result = propagate_from_assignment(assignment, delta)

    # Check assignment updated
    assignment.refresh_from_db()
    assert assignment.rating_current == 50
    assert assignment.dirty is False

    # Check fighter updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 50
    assert fighter.dirty is False

    # Check list NOT updated (propagation doesn't touch List)
    lst.refresh_from_db()
    assert lst.rating_current == 0  # Still 0!
    assert lst.stash_current == 0

    # Check return value
    assert result.old_rating == 0
    assert result.new_rating == 50
    assert result.delta == 50


@pytest.mark.django_db
def test_propagate_from_assignment_stash(
    user, make_list, content_house, make_content_fighter, make_equipment
):
    """Test assignment propagation updates fighter but NOT list (even for stash)."""
    lst = make_list("Test List")
    lst.rating_current = 0
    lst.stash_current = 0
    lst.save()

    stash_fighter_template = make_content_fighter(
        type="Stash",
        category="Crew",
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    fighter = ListFighter.objects.create(
        name="Stash Fighter",
        content_fighter=stash_fighter_template,
        list=lst,
        owner=user,
        rating_current=0,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=0,
    )

    # Propagate a cost increase
    delta = TransactDelta(old_rating=0, new_rating=50, list=lst)
    propagate_from_assignment(assignment, delta)

    # Check assignment updated
    assignment.refresh_from_db()
    assert assignment.rating_current == 50

    # Check fighter updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 50

    # Check list NOT updated (propagation doesn't touch List)
    lst.refresh_from_db()
    assert lst.rating_current == 0
    assert lst.stash_current == 0  # Still 0!


@pytest.mark.django_db
def test_propagate_from_assignment_negative_delta(
    user, make_list, content_fighter, make_equipment
):
    """Test assignment propagation handles cost decreases."""
    lst = make_list("Test List")
    lst.rating_current = 100
    lst.stash_current = 0
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=100,
    )

    # Propagate a cost decrease
    delta = TransactDelta(old_rating=100, new_rating=50, list=lst)
    result = propagate_from_assignment(assignment, delta)

    # Check assignment and fighter decreased
    assignment.refresh_from_db()
    assert assignment.rating_current == 50

    fighter.refresh_from_db()
    assert fighter.rating_current == 50

    # Check list NOT updated
    lst.refresh_from_db()
    assert lst.rating_current == 100  # Still 100!

    # Check return value
    assert result.delta == -50


@pytest.mark.django_db
def test_propagate_from_assignment_zero_delta(
    user, make_list, content_fighter, make_equipment
):
    """Test assignment propagation handles no change gracefully."""
    lst = make_list("Test List")
    lst.rating_current = 100
    lst.stash_current = 0
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=50,
        dirty=True,
    )

    # Propagate zero delta
    delta = TransactDelta(old_rating=50, new_rating=50, list=lst)
    result = propagate_from_assignment(assignment, delta)

    # Check assignment not updated when there's no change
    assignment.refresh_from_db()
    assert assignment.rating_current == 50
    # Note: dirty flag remains True because no propagation occurred

    # Check fighter not updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 100

    # Check list not updated
    lst.refresh_from_db()
    assert lst.rating_current == 100

    # Check return value indicates no change
    assert result.delta == 0


@pytest.mark.django_db
def test_propagate_from_fighter_basic(user, make_list, content_fighter):
    """Test basic fighter propagation updates fighter but NOT list."""
    lst = make_list("Test List")
    lst.rating_current = 100
    lst.stash_current = 0
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
    )

    # Propagate a fighter cost change (e.g., from advancement)
    delta = TransactDelta(old_rating=100, new_rating=150, list=lst)
    result = propagate_from_fighter(fighter, delta)

    # Check fighter updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 150
    assert fighter.dirty is False

    # Check list NOT updated (propagation doesn't touch List)
    lst.refresh_from_db()
    assert lst.rating_current == 100  # Still 100!

    # Check return value
    assert result.old_rating == 100
    assert result.new_rating == 150
    assert result.delta == 50


@pytest.mark.django_db
def test_propagate_from_fighter_stash(
    user, make_list, content_house, make_content_fighter
):
    """Test fighter propagation updates fighter but NOT list (even for stash)."""
    lst = make_list("Test List")
    lst.rating_current = 0
    lst.stash_current = 100
    lst.save()

    stash_fighter_template = make_content_fighter(
        type="Stash",
        category="Crew",
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    fighter = ListFighter.objects.create(
        name="Stash Fighter",
        content_fighter=stash_fighter_template,
        list=lst,
        owner=user,
        rating_current=100,
    )

    # Propagate a cost increase
    delta = TransactDelta(old_rating=100, new_rating=150, list=lst)
    propagate_from_fighter(fighter, delta)

    # Check fighter updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 150
    assert fighter.dirty is False

    # Check list NOT updated (propagation doesn't touch List)
    lst.refresh_from_db()
    assert lst.rating_current == 0
    assert lst.stash_current == 100  # Still 100!


@pytest.mark.django_db
def test_is_stash_linked_direct_stash_fighter(
    user, make_list, content_house, make_content_fighter
):
    """Test is_stash_linked identifies direct stash fighters."""
    lst = make_list("Test List")
    stash_fighter_template = make_content_fighter(
        type="Stash",
        category="Crew",
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    fighter = ListFighter.objects.create(
        name="Stash Fighter",
        content_fighter=stash_fighter_template,
        list=lst,
        owner=user,
    )

    assert is_stash_linked(fighter) is True


@pytest.mark.django_db
def test_is_stash_linked_regular_fighter(user, make_list, content_fighter):
    """Test is_stash_linked returns False for regular fighters."""
    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Regular Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    assert is_stash_linked(fighter) is False


@pytest.mark.django_db
def test_is_stash_linked_child_fighter_on_stash(
    user, make_list, content_house, make_content_fighter, make_equipment
):
    """Test is_stash_linked identifies child fighters linked to stash."""
    lst = make_list("Test List")

    # Create stash fighter
    stash_fighter_template = make_content_fighter(
        type="Stash",
        category="Crew",
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    stash_fighter = ListFighter.objects.create(
        name="Stash Fighter",
        content_fighter=stash_fighter_template,
        list=lst,
        owner=user,
    )

    # Create vehicle equipment on stash fighter
    vehicle_equipment = make_equipment("Vehicle", cost="100")
    vehicle_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash_fighter,
        content_equipment=vehicle_equipment,
    )

    # Create child fighter (vehicle) linked to the assignment
    vehicle_fighter_template = make_content_fighter(
        type="Vehicle",
        category="Crew",
        house=content_house,
        base_cost=100,
    )
    vehicle_fighter = ListFighter.objects.create(
        name="Vehicle",
        content_fighter=vehicle_fighter_template,
        list=lst,
        owner=user,
    )
    vehicle_assignment.child_fighter = vehicle_fighter
    vehicle_assignment.save()

    # Child fighter should be stash-linked through parent
    assert is_stash_linked(vehicle_fighter) is True


@pytest.mark.django_db
def test_is_stash_linked_child_fighter_on_regular(
    user,
    make_list,
    content_fighter,
    content_house,
    make_content_fighter,
    make_equipment,
):
    """Test is_stash_linked returns False for child fighters on regular fighters."""
    lst = make_list("Test List")

    # Create regular fighter
    regular_fighter = ListFighter.objects.create(
        name="Regular Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create vehicle equipment on regular fighter
    vehicle_equipment = make_equipment("Vehicle", cost="100")
    vehicle_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=regular_fighter,
        content_equipment=vehicle_equipment,
    )

    # Create child fighter (vehicle) linked to the assignment
    vehicle_fighter_template = make_content_fighter(
        type="Vehicle",
        category="Crew",
        house=content_house,
        base_cost=100,
    )
    vehicle_fighter = ListFighter.objects.create(
        name="Vehicle",
        content_fighter=vehicle_fighter_template,
        list=lst,
        owner=user,
    )
    vehicle_assignment.child_fighter = vehicle_fighter
    vehicle_assignment.save()

    # Child fighter should NOT be stash-linked
    assert is_stash_linked(vehicle_fighter) is False


@pytest.mark.django_db
def test_propagate_from_assignment_clamps_negative_assignment_rating(
    user, make_list, content_fighter, make_equipment
):
    """Test assignment propagation clamps negative assignment ratings to zero.

    This can happen when a cost override makes an equipment item "free" or
    negative-cost, resulting in a negative new_rating in the delta.
    """
    lst = make_list("Test List")
    lst.rating_current = 100
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=50,
        dirty=True,
    )

    # Propagate a delta that would result in negative rating
    # e.g., cost override reduced the cost below the original
    delta = TransactDelta(old_rating=50, new_rating=-10, list=lst)
    result = propagate_from_assignment(assignment, delta)

    # Assignment rating should be clamped to 0, not -10
    assignment.refresh_from_db()
    assert assignment.rating_current == 0
    assert assignment.dirty is False

    # Fighter rating should decrease by the full delta (-60)
    # but also be clamped if it goes negative
    fighter.refresh_from_db()
    assert fighter.rating_current == 40  # 100 + (-60) = 40

    # Return value reflects the actual delta values
    assert result.old_rating == 50
    assert result.new_rating == -10
    assert result.delta == -60


@pytest.mark.django_db
def test_propagate_from_assignment_clamps_negative_fighter_rating(
    user, make_list, content_fighter, make_equipment
):
    """Test assignment propagation clamps negative fighter ratings to zero.

    This can happen when the delta is large enough to make the fighter's
    total rating go negative (e.g., removing expensive equipment from a
    fighter that had a lower total).
    """
    lst = make_list("Test List")
    lst.rating_current = 50
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=50,
    )
    equipment = make_equipment("Test Equipment", cost="100")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=100,
        dirty=True,
    )

    # Propagate a large negative delta that would make fighter rating negative
    # Fighter has 50, delta is -100, would result in -50
    delta = TransactDelta(old_rating=100, new_rating=0, list=lst)
    propagate_from_assignment(assignment, delta)

    # Assignment rating should be 0
    assignment.refresh_from_db()
    assert assignment.rating_current == 0

    # Fighter rating should be clamped to 0, not -50
    fighter.refresh_from_db()
    assert fighter.rating_current == 0


@pytest.mark.django_db
def test_propagate_from_fighter_clamps_negative_rating(
    user, make_list, content_fighter
):
    """Test fighter propagation clamps negative ratings to zero.

    This can happen when a fighter's cost is reduced below zero through
    some mechanic (though rare in practice).
    """
    lst = make_list("Test List")
    lst.rating_current = 100
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=50,
        dirty=True,
    )

    # Propagate a delta that would result in negative rating
    delta = TransactDelta(old_rating=50, new_rating=-20, list=lst)
    result = propagate_from_fighter(fighter, delta)

    # Fighter rating should be clamped to 0, not -20
    fighter.refresh_from_db()
    assert fighter.rating_current == 0
    assert fighter.dirty is False

    # List should NOT be updated by propagation
    lst.refresh_from_db()
    assert lst.rating_current == 100

    # Return value reflects the actual delta values
    assert result.old_rating == 50
    assert result.new_rating == -20
    assert result.delta == -70


@pytest.mark.django_db
def test_propagate_from_assignment_skips_without_latest_action(
    user, make_list, content_fighter, make_equipment
):
    """Test assignment propagation is skipped when list has no latest_action.

    When the list action system is not enabled (no latest_action), propagation
    should be skipped and the input delta returned unchanged.
    """
    lst = make_list("Test List", create_initial_action=False)
    lst.rating_current = 0
    lst.stash_current = 0
    lst.save()
    # Note: create_initial_action=False means no latest_action, so propagation is skipped

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=0,
    )
    equipment = make_equipment("Test Equipment", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        rating_current=0,
        dirty=True,
    )

    # Propagate a cost increase - should be skipped
    delta = TransactDelta(old_rating=0, new_rating=50, list=lst)
    result = propagate_from_assignment(assignment, delta)

    # Check assignment NOT updated (propagation skipped)
    assignment.refresh_from_db()
    assert assignment.rating_current == 0
    assert assignment.dirty is True  # Still dirty

    # Check fighter NOT updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 0

    # Check return value is the same as input
    assert result is delta
    assert result.old_rating == 0
    assert result.new_rating == 50


@pytest.mark.django_db
def test_propagate_from_fighter_skips_without_latest_action(
    user, make_list, content_fighter
):
    """Test fighter propagation is skipped when list has no latest_action.

    When the list action system is not enabled (no latest_action), propagation
    should be skipped and the input delta returned unchanged.
    """
    lst = make_list("Test List", create_initial_action=False)
    lst.rating_current = 100
    lst.stash_current = 0
    lst.save()
    # Note: create_initial_action=False means no latest_action, so propagation is skipped

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
        dirty=True,
    )

    # Propagate a fighter cost change - should be skipped
    delta = TransactDelta(old_rating=100, new_rating=150, list=lst)
    result = propagate_from_fighter(fighter, delta)

    # Check fighter NOT updated (propagation skipped)
    fighter.refresh_from_db()
    assert fighter.rating_current == 100
    assert fighter.dirty is True  # Still dirty

    # Check return value is the same as input
    assert result is delta
    assert result.old_rating == 100
    assert result.new_rating == 150
