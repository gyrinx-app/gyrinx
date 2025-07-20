import pytest

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentHouse,
    ContentEquipment,
    ContentFighter,
)
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment
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


@pytest.mark.django_db
def test_wargear_excludes_fighter_category_restricted_equipment():
    """Test that wargear method excludes equipment from fighter-category-restricted categories."""
    house = ContentHouse.objects.create(name="Test House")

    # Create categories
    category_restricted = ContentEquipmentCategory.objects.create(
        name="Leader Only Equipment", group="gear"
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category_restricted,
        fighter_category=FighterCategoryChoices.LEADER,
    )

    category_normal = ContentEquipmentCategory.objects.create(
        name="Normal Equipment", group="gear"
    )

    # Create equipment
    equipment_restricted = ContentEquipment.objects.create(
        name="Leader Gun", category=category_restricted, cost="50"
    )
    equipment_normal = ContentEquipment.objects.create(
        name="Normal Gun", category=category_normal, cost="25"
    )

    # Create fighter and list
    leader_fighter = ContentFighter.objects.create(
        type="Test Leader",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )
    test_list = List.objects.create(
        name="Test List", content_house=house, status=List.CAMPAIGN_MODE
    )
    list_leader = ListFighter.objects.create(
        list=test_list, content_fighter=leader_fighter, name="My Leader"
    )

    # Assign both equipment
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_leader, content_equipment=equipment_restricted
    )
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_leader, content_equipment=equipment_normal
    )

    # Check that wargear only includes normal equipment
    wargear_names = [e.name() for e in list_leader.wargear()]
    assert "Normal Gun" in wargear_names
    assert "Leader Gun" not in wargear_names

    # Check that category restricted gear shows the restricted equipment
    assert list_leader.has_category_restricted_gear
    category_gear = list_leader.category_restricted_gearline_display
    assert len(category_gear) == 1
    assert category_gear[0]["category"] == "Leader Only Equipment"
    assert len(category_gear[0]["assignments"]) == 1
    assert category_gear[0]["assignments"][0].name() == "Leader Gun"


@pytest.mark.django_db
def test_stash_fighter_sees_all_categories():
    """Test that stash fighters can see all equipment regardless of category restrictions."""
    house = ContentHouse.objects.create(name="Test House")

    # Create categories
    category_restricted = ContentEquipmentCategory.objects.create(
        name="Leader Only Equipment", group="gear"
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category_restricted,
        fighter_category=FighterCategoryChoices.LEADER,
    )

    category_normal = ContentEquipmentCategory.objects.create(
        name="Normal Equipment", group="gear"
    )

    # Create equipment
    equipment_restricted = ContentEquipment.objects.create(
        name="Leader Gun", category=category_restricted, cost="50"
    )
    equipment_normal = ContentEquipment.objects.create(
        name="Normal Gun", category=category_normal, cost="25"
    )

    # Create stash fighter
    stash_fighter = ContentFighter.objects.create(
        type="Test Stash",
        category=FighterCategoryChoices.STASH,
        house=house,
        base_cost=0,
        is_stash=True,
    )
    test_list = List.objects.create(
        name="Test List", content_house=house, status=List.CAMPAIGN_MODE
    )
    list_stash = ListFighter.objects.create(
        list=test_list, content_fighter=stash_fighter, name="My Stash"
    )

    # Assign both equipment
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_stash, content_equipment=equipment_restricted
    )
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_stash, content_equipment=equipment_normal
    )

    # Check that stash fighter can see category restricted gear
    # (Stash fighters see all restricted categories even if they are not specifically restricted to STASH)
    assert list_stash.has_category_restricted_gear

    # Check that stash sees all restricted categories
    category_gear = list_stash.category_restricted_gearline_display
    assert len(category_gear) == 1
    assert category_gear[0]["category"] == "Leader Only Equipment"
    assert len(category_gear[0]["assignments"]) == 1
    assert category_gear[0]["assignments"][0].name() == "Leader Gun"

    # Check that wargear includes all equipment for stash
    wargear_names = [e.name() for e in list_stash.wargear()]
    assert "Normal Gun" in wargear_names
    assert "Leader Gun" in wargear_names
