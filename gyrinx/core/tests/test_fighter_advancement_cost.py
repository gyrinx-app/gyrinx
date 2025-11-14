import pytest

from gyrinx.content.models import ContentFighter
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterAdvancement,
)
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_fighter_cost_with_archived_advancement(content_house):
    """
    Test that archived advancements are NOT included in cost calculations.

    This is the ACTUAL bug: the annotation includes archived advancements,
    but it shouldn't!
    """
    # Create a list
    lst = List.objects.create(name="Test List", content_house=content_house)

    # Create fighter template (Crew)
    crew_template = ContentFighter.objects.create(
        type="Gearhead",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=50,
    )

    # Create the fighter
    fighter = ListFighter.objects.create(
        name="Test Crew",
        list=lst,
        content_fighter=crew_template,
    )

    # Add an active advancement
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="Willpower",
        xp_cost=6,
        cost_increase=5,
    )

    # Add an ARCHIVED advancement that should NOT count
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="Cool",
        xp_cost=6,
        cost_increase=10,  # This should NOT be included!
        archived=True,
    )

    # Expected costs - only the active advancement should count
    base_cost = 50
    active_advancement_cost = 5
    archived_advancement_cost = 10  # Should NOT be included
    expected_total = base_cost + active_advancement_cost  # 55, NOT 65!

    # Fetch the fighter WITH the annotation
    fighter_with_annotation = ListFighter.objects.with_related_data().get(id=fighter.id)

    # Check the annotation value
    annotated_value = fighter_with_annotation.annotated_advancement_total_cost

    # THIS IS THE BUG: The annotation will include the archived advancement!
    # It will be 15 (5 + 10) instead of 5
    print(f"annotated_advancement_total_cost = {annotated_value}")
    print(
        f"Expected: {active_advancement_cost}, but includes archived: {active_advancement_cost + archived_advancement_cost}"
    )

    # Test cost_int() - should use aggregate which filters archived correctly
    cost_int_value = fighter_with_annotation.cost_int()

    # Clear cached properties
    if hasattr(fighter_with_annotation, "cost_int_cached"):
        del fighter_with_annotation.cost_int_cached
    if hasattr(fighter_with_annotation, "_advancement_cost_int"):
        del fighter_with_annotation._advancement_cost_int

    # Test cost_int_cached() - will use the annotation which is WRONG
    cost_int_cached_value = fighter_with_annotation.cost_int_cached

    # The annotation should only include non-archived advancements
    assert annotated_value == active_advancement_cost, (
        f"BUG FOUND: annotated_advancement_total_cost is {annotated_value} "
        f"but should be {active_advancement_cost}. "
        f"The annotation is including archived advancements!"
    )

    # Both cost methods should return the correct value
    assert cost_int_value == expected_total, (
        f"cost_int() returned {cost_int_value} but expected {expected_total}"
    )

    assert cost_int_cached_value == expected_total, (
        f"cost_int_cached() returned {cost_int_cached_value} but expected {expected_total}"
    )

    # They must match each other
    assert cost_int_value == cost_int_cached_value, (
        f"cost_int() returned {cost_int_value} but "
        f"cost_int_cached() returned {cost_int_cached_value}. "
        f"These must be the same!"
    )


@pytest.mark.django_db
def test_fighter_cost_with_custom_statline_join_duplication(content_house):
    """
    Test that advancement costs are calculated correctly when fighter has a custom statline.

    This is the ACTUAL bug: when a fighter has a custom statline with multiple stats,
    the ArrayAgg annotations in with_related_data() create JOINs that cause the
    Sum annotation for advancement costs to be multiplied by the number of stats.

    Example: 1 advancement with cost_increase=5 × 5 statline stats = 25 instead of 5
    """
    from gyrinx.content.models import (
        ContentStat,
        ContentStatline,
        ContentStatlineStat,
        ContentStatlineType,
        ContentStatlineTypeStat,
    )

    # Create a list
    lst = List.objects.create(name="Test List", content_house=content_house)

    # Create fighter template (Crew)
    crew_template = ContentFighter.objects.create(
        type="Gearhead",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=50,
    )

    # Create a custom statline type
    statline_type = ContentStatlineType.objects.create(name="Test Fighter Statline")

    # Create 5 stats (matching the user's scenario)
    stats = []
    for i in range(5):
        stat = ContentStat.objects.create(
            field_name=f"test_stat_{i}",
            short_name=f"S{i}",
            full_name=f"Test Stat {i}",
            is_inverted=False,
        )
        stats.append(stat)

        # Link stat to statline type
        ContentStatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=stat,
            position=i,
            is_highlighted=False,
            is_first_of_group=(i == 0),
        )

    # Create the custom statline for the fighter template
    custom_statline = ContentStatline.objects.create(
        content_fighter=crew_template,
        statline_type=statline_type,
    )

    # Add stat values to the statline
    for i, stat_type_stat in enumerate(statline_type.stats.all()):
        ContentStatlineStat.objects.create(
            statline=custom_statline,
            statline_type_stat=stat_type_stat,
            value=str(i + 1),  # Values: 1, 2, 3, 4, 5
        )

    # Create the fighter
    fighter = ListFighter.objects.create(
        name="Test Crew",
        list=lst,
        content_fighter=crew_template,
    )

    # Add ONE advancement with cost_increase=5
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="Willpower",
        xp_cost=6,
        cost_increase=5,
    )

    # Expected costs
    base_cost = 50
    advancement_cost = 5  # Should be counted ONCE, not 5 times!
    expected_total = base_cost + advancement_cost  # 55

    # Fetch WITHOUT annotation first (should work correctly)
    fighter_no_annotation = ListFighter.objects.get(id=fighter.id)
    cost_without_annotation = fighter_no_annotation.cost_int()

    assert cost_without_annotation == expected_total, (
        f"Without annotation, cost_int() returned {cost_without_annotation} but expected {expected_total}"
    )

    # Now fetch WITH the annotation (this is where the bug manifests)
    fighter_with_annotation = ListFighter.objects.with_related_data().get(id=fighter.id)

    # Check the annotation value - THIS IS THE BUG
    annotated_value = fighter_with_annotation.annotated_advancement_total_cost

    # The annotation should be 5, NOT 25 (5 * 5 stats)
    print(f"\nDEBUG: annotated_advancement_total_cost = {annotated_value}")
    print(
        "DEBUG: Expected 5, but bug would cause it to be 25 (5 advancement cost × 5 statline stats)"
    )

    assert annotated_value == advancement_cost, (
        f"BUG CONFIRMED: annotated_advancement_total_cost is {annotated_value} but should be {advancement_cost}. "
        f"The Sum annotation is being multiplied by the number of custom statline stats ({len(stats)}) "
        f"due to JOIN duplication from the ArrayAgg annotations!"
    )

    # Test cost calculations with annotation
    cost_int_with_annotation = fighter_with_annotation.cost_int()

    # Clear cached properties
    if hasattr(fighter_with_annotation, "cost_int_cached"):
        del fighter_with_annotation.cost_int_cached
    if hasattr(fighter_with_annotation, "_advancement_cost_int"):
        del fighter_with_annotation._advancement_cost_int

    cost_int_cached_with_annotation = fighter_with_annotation.cost_int_cached

    # Both methods should return the correct total
    assert cost_int_with_annotation == expected_total, (
        f"With annotation, cost_int() returned {cost_int_with_annotation} but expected {expected_total}"
    )

    assert cost_int_cached_with_annotation == expected_total, (
        f"With annotation, cost_int_cached() returned {cost_int_cached_with_annotation} but expected {expected_total}. "
        f"Annotation value was {annotated_value}."
    )

    # They must match each other
    assert cost_int_with_annotation == cost_int_cached_with_annotation, (
        f"cost_int() returned {cost_int_with_annotation} but "
        f"cost_int_cached() returned {cost_int_cached_with_annotation}"
    )
