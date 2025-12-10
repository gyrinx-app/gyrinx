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
def test_transact_delta_properties():
    """Test TransactDelta dataclass properties."""
    # Positive delta
    delta = TransactDelta(old_rating=100, new_rating=150)
    assert delta.delta == 50
    assert delta.has_change is True

    # Negative delta
    delta = TransactDelta(old_rating=150, new_rating=100)
    assert delta.delta == -50
    assert delta.has_change is True

    # No change
    delta = TransactDelta(old_rating=100, new_rating=100)
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
    delta = TransactDelta(old_rating=0, new_rating=50)
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
    delta = TransactDelta(old_rating=0, new_rating=50)
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
    delta = TransactDelta(old_rating=100, new_rating=50)
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
    delta = TransactDelta(old_rating=50, new_rating=50)
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
    delta = TransactDelta(old_rating=100, new_rating=150)
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
    delta = TransactDelta(old_rating=100, new_rating=150)
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
