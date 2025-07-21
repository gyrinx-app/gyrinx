import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentFighterEquipmentCategoryLimit,
    ContentHouse,
    ContentEquipment,
    ContentFighter,
)
from gyrinx.content.admin import ContentFighterEquipmentCategoryLimitForm
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_content_fighter_equipment_category_limit_creation():
    """Test creating a ContentFighterEquipmentCategoryLimit."""
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(
        name="Test Limit Drive Upgrades", group="gear"
    )
    fighter = ContentFighter.objects.create(
        type="Vehicle 1",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=100,
    )

    # Create a fighter restriction first
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category,
        fighter_category=FighterCategoryChoices.VEHICLE,
    )

    # Now create the limit
    limit = ContentFighterEquipmentCategoryLimit.objects.create(
        fighter=fighter,
        equipment_category=category,
        limit=2,
    )

    assert limit.fighter == fighter
    assert limit.equipment_category == category
    assert limit.limit == 2
    assert (
        str(limit)
        == "Test House Vehicle 1 (Vehicle) - Test Limit Drive Upgrades (limit: 2)"
    )


@pytest.mark.django_db
def test_content_fighter_equipment_category_limit_validation():
    """Test that ContentFighterEquipmentCategoryLimit requires category to have fighter restrictions."""
    house = ContentHouse.objects.create(name="Test House")
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Normal Equipment", defaults={"group": "gear"}
    )
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )

    # Try to create a limit without fighter restrictions - should fail
    limit = ContentFighterEquipmentCategoryLimit(
        fighter=fighter,
        equipment_category=category,
        limit=2,
    )

    with pytest.raises(ValidationError) as exc_info:
        limit.clean()

    assert "equipment_category" in exc_info.value.error_dict
    assert "must have fighter restrictions" in str(exc_info.value)


@pytest.mark.django_db(transaction=True)
def test_category_restricted_gearline_display_with_limit():
    """Test that the category restricted gearline display shows the limit indicator."""
    house = ContentHouse.objects.create(name="Test House")

    # Create category with fighter restriction
    category = ContentEquipmentCategory.objects.create(
        name="Test Drive Upgrades", group="gear"
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category,
        fighter_category=FighterCategoryChoices.VEHICLE,
    )

    # Create equipment in that category
    equipment1 = ContentEquipment.objects.create(
        name="All-wheel steering", category=category, cost="10"
    )
    equipment2 = ContentEquipment.objects.create(
        name="Extra Armor", category=category, cost="15"
    )
    equipment3 = ContentEquipment.objects.create(
        name="Nitro Boost", category=category, cost="20"
    )

    # Create vehicle fighter
    vehicle_fighter = ContentFighter.objects.create(
        type="Vehicle 1",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=100,
    )

    # Create limit for this fighter and category
    ContentFighterEquipmentCategoryLimit.objects.create(
        fighter=vehicle_fighter,
        equipment_category=category,
        limit=2,
    )

    # Create list and list fighter
    test_list = List.objects.create(
        name="Test List", content_house=house, status=List.CAMPAIGN_MODE
    )
    list_vehicle = ListFighter.objects.create(
        list=test_list, content_fighter=vehicle_fighter, name="My Vehicle"
    )

    # Initially no equipment assigned
    gearlines = list_vehicle.category_restricted_gearline_display
    assert len(gearlines) == 1
    assert gearlines[0]["category"] == "Test Drive Upgrades"
    assert gearlines[0]["category_limit"] == "(0/2)"
    assert len(gearlines[0]["assignments"]) == 0

    # Assign one piece of equipment
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_vehicle, content_equipment=equipment1
    )

    # Get a fresh instance from the database to clear all caches
    list_vehicle = ListFighter.objects.get(pk=list_vehicle.pk)

    gearlines = list_vehicle.category_restricted_gearline_display
    assert len(gearlines) == 1
    assert gearlines[0]["category"] == "Test Drive Upgrades"
    assert gearlines[0]["category_limit"] == "(1/2)"
    assert len(gearlines[0]["assignments"]) == 1

    # Assign two more pieces (exceeding limit)
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_vehicle, content_equipment=equipment2
    )
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_vehicle, content_equipment=equipment3
    )

    # Get a fresh instance from the database to clear all caches
    list_vehicle = ListFighter.objects.get(pk=list_vehicle.pk)

    gearlines = list_vehicle.category_restricted_gearline_display
    assert len(gearlines) == 1
    assert gearlines[0]["category"] == "Test Drive Upgrades"
    assert gearlines[0]["category_limit"] == "(3/2)"  # Shows 3/2, exceeding limit
    assert len(gearlines[0]["assignments"]) == 3


@pytest.mark.django_db
def test_category_without_limit_shows_no_indicator():
    """Test that categories without limits don't show the limit indicator."""
    house = ContentHouse.objects.create(name="Test House")

    # Create category with fighter restriction but no limit
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Vehicle Equipment", defaults={"group": "gear"}
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category,
        fighter_category=FighterCategoryChoices.VEHICLE,
    )

    # Create vehicle fighter
    vehicle_fighter = ContentFighter.objects.create(
        type="Vehicle 2",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=100,
    )

    # Create list and list fighter
    test_list = List.objects.create(
        name="Test List", content_house=house, status=List.CAMPAIGN_MODE
    )
    list_vehicle = ListFighter.objects.create(
        list=test_list, content_fighter=vehicle_fighter, name="My Vehicle"
    )

    # Check that category name doesn't include limit indicator
    gearlines = list_vehicle.category_restricted_gearline_display
    assert len(gearlines) == 1
    assert gearlines[0]["category"] == "Vehicle Equipment"  # No (0/X) indicator


@pytest.mark.django_db
def test_admin_form_validation():
    """Test admin form validation for ContentFighterEquipmentCategoryLimit."""
    house = ContentHouse.objects.create(name="Test House")
    category_restricted, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Restricted Category", defaults={"group": "gear"}
    )
    category_normal, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Normal Category", defaults={"group": "gear"}
    )
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )

    # Add restriction to one category only
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category_restricted,
        fighter_category=FighterCategoryChoices.LEADER,
    )

    # Test form with category that has restrictions - should be valid
    form_data = {
        "fighter": fighter.id,
        "equipment_category": category_restricted.id,
        "limit": 3,
    }
    form = ContentFighterEquipmentCategoryLimitForm(data=form_data)
    form.parent_instance = category_restricted
    assert form.is_valid()

    # Test form with category that has no restrictions - should be invalid
    form_data["equipment_category"] = category_normal.id
    form = ContentFighterEquipmentCategoryLimitForm(data=form_data)
    form.parent_instance = category_normal
    assert not form.is_valid()
    assert "Fighter equipment category limits can only be set" in str(form.errors)
