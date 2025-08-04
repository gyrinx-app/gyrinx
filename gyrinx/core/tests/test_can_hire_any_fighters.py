import pytest
from django.contrib.auth import get_user_model

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


@pytest.mark.django_db
def test_can_hire_any_includes_all_fighters_except_stash():
    """Test that when can_hire_any is True, the form includes all fighters except stash."""
    # Create a user
    User.objects.create_user(username="testuser", password="password")

    # Create the Outcast house with can_hire_any=True
    outcast_house = ContentHouse.objects.create(
        name="Underhive Outcasts", can_hire_any=True
    )

    # Create other houses
    house1 = ContentHouse.objects.create(name="House Escher")
    house2 = ContentHouse.objects.create(name="House Goliath")
    generic_house = ContentHouse.objects.create(name="Generic House", generic=True)

    # Create various fighters
    fighter_outcast = ContentFighter.objects.create(
        type="Outcast Leader",
        house=outcast_house,
        category=FighterCategoryChoices.LEADER,
        base_cost=100,
    )
    fighter_escher = ContentFighter.objects.create(
        type="Escher Ganger",
        house=house1,
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
    )
    fighter_goliath = ContentFighter.objects.create(
        type="Goliath Champion",
        house=house2,
        category=FighterCategoryChoices.CHAMPION,
        base_cost=150,
    )
    fighter_generic = ContentFighter.objects.create(
        type="Generic Fighter",
        house=generic_house,
        category=FighterCategoryChoices.GANGER,
        base_cost=60,
    )
    fighter_exotic = ContentFighter.objects.create(
        type="Exotic Beast",
        house=house1,
        category=FighterCategoryChoices.EXOTIC_BEAST,
        base_cost=200,
    )
    fighter_vehicle = ContentFighter.objects.create(
        type="Ridgehauler",
        house=house1,
        category=FighterCategoryChoices.VEHICLE,
        base_cost=300,
    )
    fighter_stash = ContentFighter.objects.create(
        type="Stash",
        house=outcast_house,
        category=FighterCategoryChoices.STASH,
        base_cost=0,
    )

    # Test the available_for_house method directly, which is what the form uses
    available_fighters = ContentFighter.objects.available_for_house(outcast_house)

    # Verify that all fighters except stash are included
    assert fighter_outcast in available_fighters
    assert fighter_escher in available_fighters
    assert fighter_goliath in available_fighters
    assert fighter_generic in available_fighters
    assert fighter_exotic in available_fighters  # Exotic beasts should be included
    assert fighter_vehicle in available_fighters  # Vehicles should be included
    assert fighter_stash not in available_fighters  # Stash should be excluded

    # Verify the total count
    assert available_fighters.count() == 6  # All except stash


@pytest.mark.django_db
def test_normal_house_excludes_exotic_beasts_vehicles_and_other_houses():
    """Test that normal houses (can_hire_any=False) follow the original filtering rules, excluding exotic beasts and vehicles."""
    # Create a user
    User.objects.create_user(username="testuser2", password="password")

    # Create houses
    normal_house = ContentHouse.objects.create(name="House Normal", can_hire_any=False)
    other_house = ContentHouse.objects.create(name="House Other")
    generic_house = ContentHouse.objects.create(name="Generic House", generic=True)

    # Create various fighters
    fighter_normal = ContentFighter.objects.create(
        type="Normal Fighter",
        house=normal_house,
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
    )
    fighter_other = ContentFighter.objects.create(
        type="Other Fighter",
        house=other_house,
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
    )
    fighter_generic = ContentFighter.objects.create(
        type="Generic Fighter",
        house=generic_house,
        category=FighterCategoryChoices.GANGER,
        base_cost=60,
    )
    fighter_exotic = ContentFighter.objects.create(
        type="Exotic Beast",
        house=normal_house,
        category=FighterCategoryChoices.EXOTIC_BEAST,
        base_cost=200,
    )
    fighter_vehicle = ContentFighter.objects.create(
        type="Ridgehauler",
        house=normal_house,
        category=FighterCategoryChoices.VEHICLE,
        base_cost=300,
    )
    fighter_stash = ContentFighter.objects.create(
        type="Stash",
        house=normal_house,
        category=FighterCategoryChoices.STASH,
        base_cost=0,
    )

    # Test the available_for_house method directly, which is what the form uses
    available_fighters = ContentFighter.objects.available_for_house(normal_house)

    # Verify filtering rules for normal houses
    assert fighter_normal in available_fighters  # Own house fighter
    assert fighter_generic in available_fighters  # Generic house fighter
    assert fighter_other not in available_fighters  # Other house fighter excluded
    assert fighter_exotic not in available_fighters  # Exotic beasts excluded
    assert fighter_vehicle not in available_fighters  # Vehicles excluded
    assert fighter_stash not in available_fighters  # Stash excluded

    # Verify the count
    assert available_fighters.count() == 2  # Only normal and generic
