"""Tests for dead fighter cost calculations.

Dead fighters should contribute 0 to gang total cost, including their advancements.
This tests the fix for issue #1180 where dead fighters with advancements were
still contributing the advancement cost to the gang rating.
"""

import pytest

from gyrinx.content.models import ContentEquipment, ContentFighter
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterAdvancement,
)
from gyrinx.models import FighterCategoryChoices


def clear_fighter_cached_properties(fighter):
    """Clear all cached properties related to cost calculations."""
    cached_props = [
        "is_dead",
        "_advancement_cost_int",
        "cost_int_cached",
        "_base_cost_int",
    ]
    for prop in cached_props:
        if hasattr(fighter, prop):
            try:
                delattr(fighter, prop)
            except AttributeError:
                pass


@pytest.mark.django_db
def test_dead_fighter_contributes_zero_cost(content_house):
    """Test that a dead fighter contributes 0 to gang total cost."""
    lst = List.objects.create(name="Test List", content_house=content_house)

    content_fighter = ContentFighter.objects.create(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        list=lst,
        content_fighter=content_fighter,
    )

    # Fighter should have cost initially
    assert fighter.cost_int() == 50

    # Kill the fighter
    fighter.injury_state = ListFighter.DEAD
    fighter.save()
    fighter.refresh_from_db()
    clear_fighter_cached_properties(fighter)

    # Dead fighter should contribute 0
    assert fighter.is_dead is True
    assert fighter.should_have_zero_cost is True
    assert fighter.cost_int() == 0


@pytest.mark.django_db
def test_dead_fighter_with_advancement_contributes_zero_cost(content_house):
    """Test that a dead fighter with advancements contributes 0 to gang total cost.

    This is the main test for issue #1180: dead fighters were contributing
    their advancement cost to the gang rating even though they should
    contribute 0.
    """
    lst = List.objects.create(name="Test List", content_house=content_house)

    content_fighter = ContentFighter.objects.create(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=content_house,
        base_cost=100,
    )

    fighter = ListFighter.objects.create(
        name="Test Champion",
        list=lst,
        content_fighter=content_fighter,
    )

    # Add an advancement
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="Weapon Skill",
        xp_cost=6,
        cost_increase=20,
    )

    # Fighter should have base + advancement cost
    assert fighter.cost_int() == 120  # 100 + 20

    # Clear cached properties before checking again
    clear_fighter_cached_properties(fighter)

    assert fighter._advancement_cost_int == 20
    clear_fighter_cached_properties(fighter)
    assert fighter.cost_int_cached == 120

    # Kill the fighter
    fighter.injury_state = ListFighter.DEAD
    fighter.save()
    fighter.refresh_from_db()
    clear_fighter_cached_properties(fighter)

    # Dead fighter should contribute 0, including advancement
    assert fighter.is_dead is True
    assert fighter.should_have_zero_cost is True
    assert fighter._advancement_cost_int == 0  # This was the bug!
    clear_fighter_cached_properties(fighter)
    assert fighter.cost_int() == 0
    clear_fighter_cached_properties(fighter)
    assert fighter.cost_int_cached == 0


@pytest.mark.django_db
def test_dead_fighter_with_equipment_and_advancement_contributes_zero(content_house):
    """Test that dead fighter with equipment and advancement contributes 0."""
    lst = List.objects.create(name="Test List", content_house=content_house)

    content_fighter = ContentFighter.objects.create(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=content_house,
        base_cost=100,
    )

    fighter = ListFighter.objects.create(
        name="Test Champion",
        list=lst,
        content_fighter=content_fighter,
    )

    # Add equipment
    equipment = ContentEquipment.objects.create(
        name="Power Sword",
        cost=40,
    )
    fighter.assign(equipment)

    # Add an advancement
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="Weapon Skill",
        xp_cost=6,
        cost_increase=20,
    )

    # Fighter should have base + equipment + advancement cost
    assert fighter.cost_int() == 160  # 100 + 40 + 20

    # Kill the fighter
    fighter.injury_state = ListFighter.DEAD
    fighter.save()
    fighter.refresh_from_db()
    clear_fighter_cached_properties(fighter)

    # Dead fighter should contribute 0
    assert fighter.is_dead is True
    assert fighter.should_have_zero_cost is True
    assert fighter.cost_int() == 0
    clear_fighter_cached_properties(fighter)
    assert fighter.cost_int_cached == 0


@pytest.mark.django_db
def test_gang_cost_excludes_dead_fighter_advancement(content_house):
    """Test that gang total cost properly excludes dead fighter's advancement."""
    lst = List.objects.create(name="Test List", content_house=content_house)

    content_fighter = ContentFighter.objects.create(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=content_house,
        base_cost=100,
    )

    # Create two fighters
    fighter1 = ListFighter.objects.create(
        name="Alive Champion",
        list=lst,
        content_fighter=content_fighter,
    )

    fighter2 = ListFighter.objects.create(
        name="Dead Champion",
        list=lst,
        content_fighter=content_fighter,
    )

    # Add advancements to both
    ListFighterAdvancement.objects.create(
        fighter=fighter1,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="Weapon Skill",
        xp_cost=6,
        cost_increase=20,
    )

    ListFighterAdvancement.objects.create(
        fighter=fighter2,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="Ballistic Skill",
        xp_cost=6,
        cost_increase=25,
    )

    # Initial gang cost: 2 * 100 + 20 + 25 = 245
    assert lst.cost_int() == 245

    # Kill fighter2
    fighter2.injury_state = ListFighter.DEAD
    fighter2.save()

    # Gang cost should now only include alive fighter: 100 + 20 = 120
    # (Dead fighter's base cost AND advancement should be excluded)
    assert lst.cost_int() == 120


@pytest.mark.django_db
def test_should_have_zero_cost_includes_dead(content_house):
    """Test that should_have_zero_cost returns True for dead fighters."""
    lst = List.objects.create(name="Test List", content_house=content_house)

    content_fighter = ContentFighter.objects.create(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        list=lst,
        content_fighter=content_fighter,
    )

    # Active fighter should not have zero cost
    assert fighter.is_dead is False
    assert fighter.should_have_zero_cost is False

    # Dead fighter should have zero cost
    fighter.injury_state = ListFighter.DEAD
    fighter.save()
    fighter.refresh_from_db()
    clear_fighter_cached_properties(fighter)

    assert fighter.is_dead is True
    assert fighter.should_have_zero_cost is True
