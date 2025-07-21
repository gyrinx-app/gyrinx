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
def test_accessory_cost_expression_with_custom_weapon_cost():
    """Test that accessory cost expressions use the custom weapon cost when set."""
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
        cost=100,  # Base cost is 100
    )

    weapon_profile = ContentWeaponProfile.objects.create(
        name="Test Profile",
        equipment=weapon,
        cost=0,
    )

    # Create accessory with cost expression (25% of weapon cost, rounded to nearest 5)
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

    # Create assignment with custom weapon cost
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
        cost_override=50,  # Custom cost override - weapon costs 50 instead of 100
    )
    assignment.weapon_profiles_field.add(weapon_profile)
    assignment.weapon_accessories_field.add(accessory)

    # Test that accessory cost is calculated using the custom weapon cost
    # Custom weapon cost is 50, so 25% = 12.5, rounded to nearest 5 = 10 (rounds down)
    assert assignment.base_cost_int() == 50  # Custom cost
    assert assignment.weapon_accessories_cost_int() == 10
    assert assignment.cost_int() == 60  # 50 (custom weapon) + 10 (accessory)


@pytest.mark.django_db
def test_multiple_accessories_with_custom_weapon_cost():
    """Test multiple accessories with expressions using custom weapon cost."""
    # Create required content
    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        house=house,
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
    )

    category = ContentEquipmentCategory.objects.create(name="Weapons")
    weapon = ContentEquipment.objects.create(
        name="Expensive Weapon",
        category=category,
        cost=200,  # Base cost is 200
    )

    weapon_profile = ContentWeaponProfile.objects.create(
        name="Test Profile",
        equipment=weapon,
        cost=0,
    )

    # Create multiple accessories with different expressions
    accessory1 = ContentWeaponAccessory.objects.create(
        name="Telescopic Sight",
        cost=0,
        cost_expression="cost_int * 0.1",  # 10% of weapon cost
    )

    accessory2 = ContentWeaponAccessory.objects.create(
        name="Custom Grip",
        cost=0,
        cost_expression="round(cost_int * 0.05)",  # 5% rounded
    )

    accessory3 = ContentWeaponAccessory.objects.create(
        name="Extended Magazine",
        cost=20,  # Fixed cost, not an expression
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

    # Create assignment with custom weapon cost
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
        cost_override=150,  # Custom cost override - weapon costs 150 instead of 200
    )
    assignment.weapon_profiles_field.add(weapon_profile)
    assignment.weapon_accessories_field.add(accessory1, accessory2, accessory3)

    # Test that accessory costs are calculated correctly
    # Custom weapon cost is 150
    # Accessory 1: 150 * 0.1 = 15
    # Accessory 2: round(150 * 0.05) = 8
    # Accessory 3: 20 (fixed cost)
    # Total accessories: 15 + 8 + 20 = 43
    assert assignment.base_cost_int() == 150  # Custom cost
    assert assignment.weapon_accessories_cost_int() == 43
    assert assignment.cost_int() == 193  # 150 (custom weapon) + 43 (accessories)


@pytest.mark.django_db
def test_ui_displays_custom_weapon_cost_with_calculated_accessory():
    """Test that accessory selection and cost calculation work with custom weapon costs."""
    # Create required content
    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        house=house,
        type="Test Fighter",
        category=FighterCategoryChoices.CHAMPION,
        base_cost=80,
    )

    category = ContentEquipmentCategory.objects.create(name="Weapons")
    weapon = ContentEquipment.objects.create(
        name="Basic Weapon",
        category=category,
        cost=10,  # Base cost is 10
    )

    weapon_profile = ContentWeaponProfile.objects.create(
        name="Test Profile",
        equipment=weapon,
        cost=0,
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

    # Create assignment with custom weapon cost
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
        cost_override=40,  # Custom cost override - weapon costs 40 instead of 10
    )
    assignment.weapon_profiles_field.add(weapon_profile)
    assignment.weapon_accessories_field.add(accessory)

    # Verify the accessory cost is calculated based on custom weapon cost
    # Custom weapon cost is 40, so 25% = 10, no rounding needed
    assert assignment.base_cost_int() == 40  # Custom cost
    assert assignment.weapon_accessories_cost_int() == 10
    assert assignment.cost_int() == 50  # 40 (custom weapon) + 10 (accessory)


@pytest.mark.django_db
def test_accessory_cost_expression_with_zero_custom_cost():
    """Test that accessory cost expressions handle zero custom weapon cost correctly."""
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

    # Create assignment with zero custom cost (free weapon)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
        cost_override=0,  # Weapon is free
    )
    assignment.weapon_profiles_field.add(weapon_profile)
    assignment.weapon_accessories_field.add(accessory)

    # Test that accessory cost is calculated correctly with zero weapon cost
    # Weapon cost is 0, so 25% = 0
    assert assignment.base_cost_int() == 0  # Free weapon
    assert assignment.weapon_accessories_cost_int() == 0
    assert assignment.cost_int() == 0  # 0 (weapon) + 0 (accessory)


@pytest.mark.django_db
def test_accessory_calculated_costs_with_mixed_types():
    """Test mixing calculated and fixed cost accessories with custom weapon costs."""
    # Create required content
    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        house=house,
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
    )

    category = ContentEquipmentCategory.objects.create(name="Weapons")
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=category,
        cost=20,
    )

    weapon_profile = ContentWeaponProfile.objects.create(
        name="Test Profile",
        equipment=weapon,
        cost=0,
    )

    # Create multiple accessories
    accessory1 = ContentWeaponAccessory.objects.create(
        name="Master Crafted",
        cost=0,
        cost_expression="round(cost_int * 0.25 / 5) * 5",
    )

    accessory2 = ContentWeaponAccessory.objects.create(
        name="Telescopic Sight",
        cost=0,
        cost_expression="cost_int * 0.5",  # 50% of weapon cost
    )

    accessory3 = ContentWeaponAccessory.objects.create(
        name="Silencer",
        cost=15,  # Fixed cost
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

    # Create assignment with custom weapon cost
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
        cost_override=60,  # Custom cost override
    )
    assignment.weapon_profiles_field.add(weapon_profile)
    assignment.weapon_accessories_field.add(accessory1, accessory2, accessory3)

    # Test that accessory costs are calculated correctly
    # For weapon cost 60:
    # - Master Crafted: 25% = 15
    # - Telescopic Sight: 50% = 30
    # - Silencer: fixed 15
    assert assignment.base_cost_int() == 60  # Custom cost
    assert assignment.weapon_accessories_cost_int() == 60  # 15 + 30 + 15
    assert assignment.cost_int() == 120  # 60 (weapon) + 60 (accessories)
