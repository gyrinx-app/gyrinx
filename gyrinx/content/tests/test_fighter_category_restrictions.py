import pytest

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentHouse,
)
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_fighter_category_restriction_creation():
    """Test creating a fighter category restriction."""
    category = ContentEquipmentCategory.objects.create(name="Leader Gear", group="gear")
    restriction = ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category,
        fighter_category=FighterCategoryChoices.LEADER,
    )
    assert restriction.equipment_category == category
    assert restriction.fighter_category == FighterCategoryChoices.LEADER
    assert str(restriction) == "Leader Gear - Leader"


@pytest.mark.django_db
def test_equipment_category_fighter_restrictions():
    """Test equipment category methods for fighter restrictions."""
    category = ContentEquipmentCategory.objects.create(
        name="Champion Gear", group="gear"
    )

    # No restrictions initially
    assert category.get_fighter_category_restrictions() == []
    assert category.is_available_to_fighter_category(FighterCategoryChoices.LEADER)
    assert category.is_available_to_fighter_category(FighterCategoryChoices.CHAMPION)

    # Add restrictions
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category,
        fighter_category=FighterCategoryChoices.CHAMPION,
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category,
        fighter_category=FighterCategoryChoices.LEADER,
    )

    # Check restrictions
    restrictions = category.get_fighter_category_restrictions()
    assert len(restrictions) == 2
    assert FighterCategoryChoices.CHAMPION in restrictions
    assert FighterCategoryChoices.LEADER in restrictions

    # Check availability
    assert category.is_available_to_fighter_category(FighterCategoryChoices.LEADER)
    assert category.is_available_to_fighter_category(FighterCategoryChoices.CHAMPION)
    assert not category.is_available_to_fighter_category(FighterCategoryChoices.GANGER)
    assert not category.is_available_to_fighter_category(FighterCategoryChoices.JUVE)


@pytest.mark.django_db
def test_fighter_category_and_house_restrictions():
    """Test that both fighter category and house restrictions work together (AND rule)."""
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(
        name="Special Gear", group="gear"
    )

    # Add both house and fighter category restrictions
    category.restricted_to.add(house)
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category,
        fighter_category=FighterCategoryChoices.LEADER,
    )

    # Category should only be available to leaders from the specific house
    assert category.is_available_to_fighter_category(FighterCategoryChoices.LEADER)
    assert not category.is_available_to_fighter_category(
        FighterCategoryChoices.CHAMPION
    )

    # Both conditions must be met (AND rule)
    assert category.restricted_to.filter(id=house.id).exists()
    assert FighterCategoryChoices.LEADER in category.get_fighter_category_restrictions()
