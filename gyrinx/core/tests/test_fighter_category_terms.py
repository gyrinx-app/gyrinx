import pytest

from gyrinx.content.models import (
    ContentFighter,
    ContentFighterCategoryTerms,
    ContentHouse,
)
from gyrinx.core.models.list import List, ListFighter
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_fighter_default_terms(content_house):
    """Test that fighters without custom terms return default values."""
    # Create a regular fighter
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=content_house)
    list_fighter = ListFighter.objects.create(
        list=lst, content_fighter=content_fighter, name="Test Ganger"
    )

    # Test default terms
    assert list_fighter.term_singular == "Fighter"
    assert list_fighter.term_proximal_demonstrative == "This fighter"
    assert list_fighter.term_injury_singular == "Injury"
    assert list_fighter.term_injury_plural == "Injuries"

    # Test backward compatibility
    assert list_fighter.proximal_demonstrative == "This fighter"


@pytest.mark.django_db
def test_vehicle_custom_terms():
    """Test that vehicles can have custom terms."""
    # Create a vehicle house
    vehicle_house = ContentHouse.objects.create(name="Vehicle House")

    # Create a vehicle fighter
    vehicle_fighter = ContentFighter.objects.create(
        type="Test Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=vehicle_house,
        base_cost=200,
    )

    # Create custom terms for vehicles
    ContentFighterCategoryTerms.objects.create(
        categories=[FighterCategoryChoices.VEHICLE],
        singular="Vehicle",
        proximal_demonstrative="The vehicle",
        injury_singular="Damage",
        injury_plural="Damage",
    )

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=vehicle_house)
    list_fighter = ListFighter.objects.create(
        list=lst, content_fighter=vehicle_fighter, name="Test Vehicle"
    )

    # Test custom terms
    assert list_fighter.term_singular == "Vehicle"
    assert list_fighter.term_proximal_demonstrative == "The vehicle"
    assert list_fighter.term_injury_singular == "Damage"
    assert list_fighter.term_injury_plural == "Damage"


@pytest.mark.django_db
def test_stash_custom_terms():
    """Test that stash can have custom terms."""
    # Create a house
    house = ContentHouse.objects.create(name="Test House")

    # Create a stash fighter
    stash_fighter = ContentFighter.objects.create(
        type="Stash",
        category=FighterCategoryChoices.STASH,
        house=house,
        base_cost=0,
        is_stash=True,
    )

    # Create custom terms for stash
    ContentFighterCategoryTerms.objects.create(
        categories=[FighterCategoryChoices.STASH],
        singular="Stash",
        proximal_demonstrative="The stash",
        injury_singular="Wear",
        injury_plural="Wear",
    )

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house)
    list_fighter = ListFighter.objects.create(
        list=lst, content_fighter=stash_fighter, name="Stash"
    )

    # Test custom terms override default stash logic
    assert list_fighter.term_singular == "Stash"
    assert list_fighter.term_proximal_demonstrative == "The stash"
    assert list_fighter.term_injury_singular == "Wear"
    assert list_fighter.term_injury_plural == "Wear"


@pytest.mark.django_db
def test_default_fallback_for_vehicle_without_terms():
    """Test that vehicles without custom terms still get appropriate defaults."""
    # Create a vehicle house
    vehicle_house = ContentHouse.objects.create(name="Vehicle House")

    # Create a vehicle fighter without custom terms
    vehicle_fighter = ContentFighter.objects.create(
        type="Test Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=vehicle_house,
        base_cost=200,
    )

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=vehicle_house)
    list_fighter = ListFighter.objects.create(
        list=lst, content_fighter=vehicle_fighter, name="Test Vehicle"
    )

    # Test default fallback for vehicles
    assert list_fighter.term_singular == "Fighter"
    # This is the only one that should be different in the fallback case
    assert list_fighter.term_proximal_demonstrative == "The vehicle"
    assert list_fighter.term_injury_singular == "Injury"
    assert list_fighter.term_injury_plural == "Injuries"


@pytest.mark.django_db
def test_default_fallback_for_stash_without_terms():
    """Test that stash without custom terms still get appropriate defaults."""
    # Create a house
    house = ContentHouse.objects.create(name="Test House")

    # Create a stash fighter without custom terms
    stash_fighter = ContentFighter.objects.create(
        type="Stash",
        category=FighterCategoryChoices.STASH,
        house=house,
        base_cost=0,
        is_stash=True,
    )

    # Create a list and list fighter
    lst = List.objects.create(name="Test List", content_house=house)
    list_fighter = ListFighter.objects.create(
        list=lst, content_fighter=stash_fighter, name="Stash"
    )

    # Test default fallback for stash
    assert list_fighter.term_singular == "Fighter"
    # This is the only one that should be different in the fallback case
    assert list_fighter.term_proximal_demonstrative == "The stash"
    assert list_fighter.term_injury_singular == "Injury"
    assert list_fighter.term_injury_plural == "Injuries"


@pytest.mark.django_db
def test_multiple_categories_can_share_terms():
    """Test that multiple fighter categories can share the same terms."""
    house = ContentHouse.objects.create(name="Test House")

    # Create different category fighters
    specialist = ContentFighter.objects.create(
        type="Specialist",
        category=FighterCategoryChoices.SPECIALIST,
        house=house,
        base_cost=100,
    )

    champion = ContentFighter.objects.create(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=house,
        base_cost=150,
    )

    # Create shared terms for both specialists and champions
    ContentFighterCategoryTerms.objects.create(
        categories=[FighterCategoryChoices.SPECIALIST, FighterCategoryChoices.CHAMPION],
        singular="Elite",
        proximal_demonstrative="This elite",
        injury_singular="Wound",
        injury_plural="Wounds",
    )

    # Create list fighters
    lst = List.objects.create(name="Test List", content_house=house)

    list_specialist = ListFighter.objects.create(
        list=lst, content_fighter=specialist, name="Specialist Fighter"
    )

    list_champion = ListFighter.objects.create(
        list=lst, content_fighter=champion, name="Champion Fighter"
    )

    # Test that both use the same terms
    assert list_specialist.term_singular == "Elite"
    assert list_specialist.term_proximal_demonstrative == "This elite"
    assert list_specialist.term_injury_singular == "Wound"
    assert list_specialist.term_injury_plural == "Wounds"

    assert list_champion.term_singular == "Elite"
    assert list_champion.term_proximal_demonstrative == "This elite"
    assert list_champion.term_injury_singular == "Wound"
    assert list_champion.term_injury_plural == "Wounds"
