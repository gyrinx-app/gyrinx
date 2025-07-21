import pytest
from django.contrib.auth.models import User

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    FighterCategoryChoices,
)
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment


@pytest.mark.django_db
def test_assignment_with_accessory_cost_expression():
    """Test that equipment assignments use accessory cost expressions."""
    # Create required content
    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        house=house,
        type="Test Fighter",
        category=FighterCategoryChoices.LEADER,
        base_cost=100,
    )

    category = ContentEquipmentCategory.objects.create(name="Weapons")
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=category,
        cost=100,
    )

    weapon_profile = ContentWeaponProfile.objects.create(
        name="Test Profile",
        equipment=weapon,
        cost=0,  # Standard profile
    )

    # Create accessory with cost expression
    accessory = ContentWeaponAccessory.objects.create(
        name="Master Crafted",
        cost=0,
        cost_expression="round(cost_int * 0.25 / 5) * 5",
    )

    # Create user and list
    user = User.objects.create_user(username="testuser")
    gang_list = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
    )

    list_fighter = ListFighter.objects.create(
        list=gang_list,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Create assignment with accessory
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
    )
    assignment.weapon_profiles_field.add(weapon_profile)
    assignment.weapon_accessories_field.add(accessory)

    # Test that accessory cost is calculated using expression
    # Weapon base cost is 100, so 25% rounded up to nearest 5 = 25
    assert assignment.weapon_accessories_cost_int() == 25
    assert assignment.cost_int() == 125  # 100 (weapon) + 25 (accessory)


@pytest.mark.django_db
def test_assignment_with_multiple_accessories_with_expressions():
    """Test that multiple accessories with expressions calculate correctly."""
    # Create required content
    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        house=house,
        type="Test Fighter",
        category=FighterCategoryChoices.LEADER,
        base_cost=100,
    )

    category = ContentEquipmentCategory.objects.create(name="Weapons")
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=category,
        cost=200,
    )

    weapon_profile = ContentWeaponProfile.objects.create(
        name="Test Profile",
        equipment=weapon,
        cost=0,
    )

    # Create accessories with different cost expressions
    accessory1 = ContentWeaponAccessory.objects.create(
        name="Accessory 1",
        cost=0,
        cost_expression="cost_int * 0.1",  # 10% of base cost
    )

    accessory2 = ContentWeaponAccessory.objects.create(
        name="Accessory 2",
        cost=0,
        cost_expression="round(cost_int * 0.15)",  # 15% rounded
    )

    # Create user and list
    user = User.objects.create_user(username="testuser")
    gang_list = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
    )

    list_fighter = ListFighter.objects.create(
        list=gang_list,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Create assignment with accessories
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
    )
    assignment.weapon_profiles_field.add(weapon_profile)
    assignment.weapon_accessories_field.add(accessory1, accessory2)

    # Test that accessory costs are calculated using expressions
    # Weapon base cost is 200
    # Accessory 1: 200 * 0.1 = 20
    # Accessory 2: round(200 * 0.15) = 30
    # Total accessories: 20 + 30 = 50
    assert assignment.weapon_accessories_cost_int() == 50
    assert assignment.cost_int() == 250  # 200 (weapon) + 50 (accessories)


@pytest.mark.django_db
def test_assignment_with_accessory_without_expression():
    """Test that accessories without expressions use base cost."""
    # Create required content
    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        house=house,
        type="Test Fighter",
        category=FighterCategoryChoices.LEADER,
        base_cost=100,
    )

    category = ContentEquipmentCategory.objects.create(name="Weapons")
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=category,
        cost=100,
    )

    weapon_profile = ContentWeaponProfile.objects.create(
        name="Test Profile",
        equipment=weapon,
        cost=0,
    )

    # Create accessory without cost expression
    accessory = ContentWeaponAccessory.objects.create(
        name="Regular Accessory",
        cost=30,  # Fixed cost
    )

    # Create user and list
    user = User.objects.create_user(username="testuser")
    gang_list = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
    )

    list_fighter = ListFighter.objects.create(
        list=gang_list,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Create assignment with accessory
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
    )
    assignment.weapon_profiles_field.add(weapon_profile)
    assignment.weapon_accessories_field.add(accessory)

    # Test that accessory uses base cost
    assert assignment.weapon_accessories_cost_int() == 30
    assert assignment.cost_int() == 130  # 100 (weapon) + 30 (accessory)
