import pytest
from django.apps import apps

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.models import List, ListFighter, ListFighterAdvancement
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_fix_movement_advances_migration():
    """Test the fix_movement_advances migration function."""
    # Get the migration
    migration_module = __import__(
        "gyrinx.core.migrations.0088_auto_20250731_1146",
        fromlist=["fix_movement_advances"],
    )
    fix_movement_advances = migration_module.fix_movement_advances

    # Create test data
    # Create a house
    house = ContentHouse.objects.create(
        name="Test House",
    )

    # Create a content fighter with movement of 4"
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
        movement='4"',
        weapon_skill="3+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7",
        cool="7",
        willpower="7",
        intelligence="7",
    )

    # Create a list and list fighter
    test_list = List.objects.create(
        name="Test List",
        content_house=house,
        credits_current=1000,
    )

    # Test case 1: Fighter with movement advancement and override equals base
    fighter1 = ListFighter.objects.create(
        content_fighter=content_fighter,
        list=test_list,
        name="Fighter 1",
        movement_override='4"',  # Same as base, should be fixed
    )

    # Create movement advancement for fighter1
    ListFighterAdvancement.objects.create(
        fighter=fighter1,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="movement",
        xp_cost=6,
    )

    # Test case 2: Fighter with movement advancement and override already incremented
    fighter2 = ListFighter.objects.create(
        content_fighter=content_fighter,
        list=test_list,
        name="Fighter 2",
        movement_override='5"',  # Already incremented, should not be changed
    )

    ListFighterAdvancement.objects.create(
        fighter=fighter2,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="movement",
        xp_cost=6,
    )

    # Test case 3: Fighter with movement advancement but no override
    fighter3 = ListFighter.objects.create(
        content_fighter=content_fighter,
        list=test_list,
        name="Fighter 3",
        movement_override=None,  # No override, should not be changed
    )

    ListFighterAdvancement.objects.create(
        fighter=fighter3,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="movement",
        xp_cost=6,
    )

    # Test case 4: Fighter without movement advancement
    fighter4 = ListFighter.objects.create(
        content_fighter=content_fighter,
        list=test_list,
        name="Fighter 4",
        movement_override='4"',  # Same as base but no advancement
    )

    # Run the migration
    fix_movement_advances(apps, None)

    # Refresh from database
    fighter1.refresh_from_db()
    fighter2.refresh_from_db()
    fighter3.refresh_from_db()
    fighter4.refresh_from_db()

    # Check results
    assert fighter1.movement_override == '5"', (
        'Fighter 1 should have movement incremented from 4" to 5"'
    )
    assert fighter2.movement_override == '5"', 'Fighter 2 should remain at 5"'
    assert fighter3.movement_override is None, "Fighter 3 should still have no override"
    assert fighter4.movement_override == '4"', (
        'Fighter 4 should remain at 4" (no advancement)'
    )


@pytest.mark.django_db
def test_fix_movement_advances_without_quotes():
    """Test the migration handles movement values without quotes."""
    migration_module = __import__(
        "gyrinx.core.migrations.0088_auto_20250731_1146",
        fromlist=["fix_movement_advances"],
    )
    fix_movement_advances = migration_module.fix_movement_advances

    # Create house
    house = ContentHouse.objects.create(
        name="Test House No Quotes",
    )

    # Create content fighter with movement without quotes
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter No Quotes",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
        movement="4",  # No quotes
        weapon_skill="3+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7",
        cool="7",
        willpower="7",
        intelligence="7",
    )

    test_list = List.objects.create(
        name="Test List No Quotes",
        content_house=house,
        credits_current=1000,
    )

    fighter = ListFighter.objects.create(
        content_fighter=content_fighter,
        list=test_list,
        name="Fighter No Quotes",
        movement_override="4",  # Same as base, no quotes
    )

    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="movement",
        xp_cost=6,
    )

    # Run the migration
    fix_movement_advances(apps, None)

    fighter.refresh_from_db()

    # Should increment without adding quotes
    assert fighter.movement_override == "5", (
        "Movement should be incremented from 4 to 5 without quotes"
    )


@pytest.mark.django_db
def test_fix_movement_advances_edge_cases():
    """Test edge cases for the migration."""
    migration_module = __import__(
        "gyrinx.core.migrations.0088_auto_20250731_1146",
        fromlist=["fix_movement_advances"],
    )
    fix_movement_advances = migration_module.fix_movement_advances

    # Create house
    house = ContentHouse.objects.create(
        name="Test House Edge",
    )

    # Create content fighter
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter Edge",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
        movement='4"',
        weapon_skill="3+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7",
        cool="7",
        willpower="7",
        intelligence="7",
    )

    test_list = List.objects.create(
        name="Test List Edge",
        content_house=house,
        credits_current=1000,
    )

    # Test case: Non-numeric movement value
    fighter_non_numeric = ListFighter.objects.create(
        content_fighter=content_fighter,
        list=test_list,
        name="Fighter Non-numeric",
        movement_override="N/A",  # Non-numeric
    )

    ListFighterAdvancement.objects.create(
        fighter=fighter_non_numeric,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="movement",
        xp_cost=6,
    )

    # Run the migration - should not crash
    fix_movement_advances(apps, None)

    fighter_non_numeric.refresh_from_db()

    # Should remain unchanged
    assert fighter_non_numeric.movement_override == "N/A", (
        "Non-numeric movement should remain unchanged"
    )
