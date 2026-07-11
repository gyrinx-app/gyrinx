"""Tests for cost propagation functions."""

import pytest

from gyrinx.core.cost.propagation import (
    Delta,
    propagate_from_assignment,
    propagate_from_fighter,
)
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment


@pytest.mark.django_db
def test_transact_delta_properties(make_list):
    """Test TransactDelta dataclass properties."""
    lst = make_list("Test List")

    # Positive delta
    delta = Delta(delta=50, list=lst)
    assert delta.has_change is True

    # Negative delta
    delta = Delta(delta=-50, list=lst)
    assert delta.has_change is True

    # No change
    delta = Delta(delta=0, list=lst)
    assert delta.has_change is False


@pytest.mark.django_db
def test_propagate_from_assignment_basic(
    user, make_list, content_fighter, make_equipment
):
    """Test basic assignment propagation updates assignment, fighter, and list."""

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
    delta = Delta(delta=50, list=lst)
    propagate_from_assignment(assignment, delta)

    # Check assignment updated
    assignment.refresh_from_db()
    assert assignment.rating_current == 50
    assert assignment.dirty is False

    # Check fighter updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 50
    assert fighter.dirty is False

    # Check list rating updated (regular fighter's gear moves the rating book)
    lst.refresh_from_db()
    assert lst.rating_current == 50
    assert lst.stash_current == 0


@pytest.mark.django_db
def test_propagate_from_assignment_stash(
    user, make_list, content_house, make_content_fighter, make_equipment
):
    """Test assignment propagation on stash gear moves the list's stash book."""

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
    delta = Delta(delta=50, list=lst)
    propagate_from_assignment(assignment, delta)

    # Check assignment updated
    assignment.refresh_from_db()
    assert assignment.rating_current == 50

    # Check fighter updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 50

    # Check list stash updated (stash fighter's gear moves the stash book)
    lst.refresh_from_db()
    assert lst.rating_current == 0
    assert lst.stash_current == 50


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
    delta = Delta(delta=-50, list=lst)
    result = propagate_from_assignment(assignment, delta)

    # Check assignment and fighter decreased
    assignment.refresh_from_db()
    assert assignment.rating_current == 50

    fighter.refresh_from_db()
    assert fighter.rating_current == 50

    # Check list updated by the negative delta
    lst.refresh_from_db()
    assert lst.rating_current == 50

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
    delta = Delta(delta=0, list=lst)
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
    """Test basic fighter propagation updates fighter and list."""

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
    delta = Delta(delta=50, list=lst)
    propagate_from_fighter(fighter, delta)

    # Check fighter updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 150
    assert fighter.dirty is False

    # Check list updated (regular fighter moves the rating book)
    lst.refresh_from_db()
    assert lst.rating_current == 150


@pytest.mark.django_db
def test_propagate_from_fighter_stash(
    user, make_list, content_house, make_content_fighter
):
    """Test fighter propagation on the stash fighter moves the stash book."""

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
    delta = Delta(delta=50, list=lst)
    propagate_from_fighter(fighter, delta)

    # Check fighter updated
    fighter.refresh_from_db()
    assert fighter.rating_current == 150
    assert fighter.dirty is False

    # Check list stash updated (stash fighter moves the stash book)
    lst.refresh_from_db()
    assert lst.rating_current == 0
    assert lst.stash_current == 150


@pytest.mark.django_db
def test_propagate_from_assignment_allows_negative_assignment_rating(
    user, make_list, content_fighter, make_equipment
):
    """Test assignment propagation allows negative assignment ratings.

    This can happen when a cost override makes an equipment item "free" or
    negative-cost, resulting in a negative rating.
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

    # Propagate a delta that results in negative rating
    # e.g., cost override reduced the cost below the original
    delta = Delta(delta=-60, list=lst)
    propagate_from_assignment(assignment, delta)

    # Assignment rating should be negative (50 + (-60) = -10)
    assignment.refresh_from_db()
    assert assignment.rating_current == -10
    assert assignment.dirty is False

    # Fighter rating should decrease by the full delta
    fighter.refresh_from_db()
    assert fighter.rating_current == 40  # 100 + (-60) = 40


@pytest.mark.django_db
def test_propagate_from_assignment_allows_negative_fighter_rating(
    user, make_list, content_fighter, make_equipment
):
    """Test assignment propagation allows negative fighter ratings.

    This can happen when equipment has negative cost (e.g., Goliath
    gene-smithing), making the fighter's total rating negative.
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

    # Propagate a large negative delta
    # Fighter has 50, delta is -100, result is -50
    delta = Delta(delta=-100, list=lst)
    propagate_from_assignment(assignment, delta)

    # Assignment rating should be 0 (100 + (-100) = 0)
    assignment.refresh_from_db()
    assert assignment.rating_current == 0

    # Fighter rating should be -50 (50 + (-100) = -50)
    fighter.refresh_from_db()
    assert fighter.rating_current == -50


@pytest.mark.django_db
def test_propagate_from_fighter_allows_negative_rating(
    user, make_list, content_fighter
):
    """Test fighter propagation allows negative ratings.

    This can happen when a fighter's cost is reduced below zero through
    negative-cost equipment (e.g., Goliath gene-smithing).
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

    # Propagate a delta that results in negative rating
    delta = Delta(delta=-70, list=lst)
    propagate_from_fighter(fighter, delta)

    # Fighter rating should be -20 (50 + (-70) = -20)
    fighter.refresh_from_db()
    assert fighter.rating_current == -20
    assert fighter.dirty is False

    # List rating moves by the delta, clamped at zero (the field is
    # positive-only even though fighter caches can go negative)
    lst.refresh_from_db()
    assert lst.rating_current == 30
