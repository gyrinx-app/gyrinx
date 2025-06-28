"""
Comprehensive tests for cost calculation methods across content models.

This test file ensures all cost-related methods (cost_int, cost_display,
cost_for_fighter_int) work correctly before implementing the CostMixin.
"""

import pytest

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
    ContentHouse,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.models import FighterCategoryChoices


# ContentEquipment cost methods tests


@pytest.mark.django_db
def test_content_equipment_cost_int_with_integer_string():
    """Test cost_int with a valid integer string."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category, cost="100"
    )
    assert equipment.cost_int() == 100


@pytest.mark.django_db
def test_content_equipment_cost_int_with_empty_string():
    """Test cost_int with empty string returns 0."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category, cost=""
    )
    assert equipment.cost_int() == 0


@pytest.mark.django_db
def test_content_equipment_cost_int_with_non_integer_string():
    """Test cost_int with non-integer string returns 0."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category, cost="2D6X10"
    )
    assert equipment.cost_int() == 0


@pytest.mark.django_db
def test_content_equipment_cost_display_with_integer_cost():
    """Test cost_display with integer cost shows currency symbol."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category, cost="50"
    )
    assert equipment.cost_display() == "50¢"


@pytest.mark.django_db
def test_content_equipment_cost_display_with_non_integer_cost():
    """Test cost_display with non-integer cost shows as-is."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category, cost="2D6X10"
    )
    assert equipment.cost_display() == "2D6X10"


@pytest.mark.django_db
def test_content_equipment_cost_display_with_empty_cost():
    """Test cost_display with empty cost returns empty string."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category, cost=""
    )
    assert equipment.cost_display() == ""


@pytest.mark.django_db
def test_content_equipment_cost_for_fighter_int_without_annotation():
    """Test cost_for_fighter_int raises error without annotation."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category, cost="100"
    )
    with pytest.raises(AttributeError, match="cost_for_fighter not available"):
        equipment.cost_for_fighter_int()


@pytest.mark.django_db
def test_content_equipment_cost_for_fighter_int_with_annotation():
    """Test cost_for_fighter_int with fighter-specific cost override."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category, cost="100"
    )

    # Create override
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=equipment, cost=75
    )

    # Get equipment with annotation
    equipment_with_cost = ContentEquipment.objects.with_cost_for_fighter(
        fighter
    ).get(pk=equipment.pk)
    assert equipment_with_cost.cost_for_fighter_int() == 75


# ContentWeaponProfile cost methods tests


@pytest.mark.django_db
def test_content_weapon_profile_cost_int():
    """Test cost_int returns the integer cost."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Weapons & Ammo"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Weapon", category=category
    )
    profile = ContentWeaponProfile.objects.create(
        equipment=equipment, name="Long Range", cost=25
    )
    assert profile.cost_int() == 25


@pytest.mark.django_db
def test_content_weapon_profile_cost_display_for_standard_profile():
    """Test cost_display for standard (unnamed) profile returns empty."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Weapons & Ammo"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Weapon", category=category
    )
    profile = ContentWeaponProfile.objects.create(
        equipment=equipment,
        name="",  # Standard profile
        cost=0,
    )
    assert profile.cost_display() == ""


@pytest.mark.django_db
def test_content_weapon_profile_cost_display_for_named_profile_with_positive_cost():
    """Test cost_display for named profile shows cost with sign."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Weapons & Ammo"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Weapon", category=category
    )
    profile = ContentWeaponProfile.objects.create(
        equipment=equipment, name="Long Range", cost=25
    )
    assert profile.cost_display() == "+25¢"


@pytest.mark.django_db
def test_content_weapon_profile_cost_display_for_named_profile_with_zero_cost():
    """Test cost_display for named profile with zero cost returns empty."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Weapons & Ammo"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Weapon", category=category
    )
    profile = ContentWeaponProfile.objects.create(
        equipment=equipment, name="Special", cost=0
    )
    assert profile.cost_display() == ""


@pytest.mark.django_db
def test_content_weapon_profile_cost_for_fighter_int_with_override():
    """Test cost_for_fighter_int with fighter-specific override."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Weapons & Ammo"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Weapon", category=category
    )
    profile = ContentWeaponProfile.objects.create(
        equipment=equipment, name="Long Range", cost=25
    )

    # Create override
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=equipment, weapon_profile=profile, cost=20
    )

    # Get profile with annotation
    profile_with_cost = ContentWeaponProfile.objects.with_cost_for_fighter(
        fighter
    ).get(pk=profile.pk)
    assert profile_with_cost.cost_for_fighter_int() == 20


# ContentWeaponAccessory cost methods tests


@pytest.mark.django_db
def test_content_weapon_accessory_cost_int():
    """Test cost_int returns the integer cost."""
    accessory = ContentWeaponAccessory.objects.create(name="Test Scope", cost=15)
    assert accessory.cost_int() == 15


@pytest.mark.django_db
def test_content_weapon_accessory_cost_display():
    """Test cost_display formats cost with currency symbol."""
    accessory = ContentWeaponAccessory.objects.create(name="Test Scope", cost=15)
    assert accessory.cost_display() == "15¢"


@pytest.mark.django_db
def test_content_weapon_accessory_cost_display_negative():
    """Test cost_display with negative cost."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Discount Scope", cost=-5
    )
    assert accessory.cost_display() == "-5¢"


@pytest.mark.django_db
def test_content_weapon_accessory_cost_for_fighter_int_with_override():
    """Test cost_for_fighter_int with fighter-specific override."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    accessory = ContentWeaponAccessory.objects.create(name="Test Scope", cost=15)

    # Create override
    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=fighter, weapon_accessory=accessory, cost=10
    )

    # Get accessory with annotation
    accessory_with_cost = ContentWeaponAccessory.objects.with_cost_for_fighter(
        fighter
    ).get(pk=accessory.pk)
    assert accessory_with_cost.cost_for_fighter_int() == 10


# ContentEquipmentUpgrade cost methods tests


@pytest.mark.django_db
def test_content_equipment_upgrade_cost_int_single_mode():
    """Test cost_int in SINGLE mode sums all upgrades up to position."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Cyberteknika",
        category=category,
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
    )

    # Create upgrades with cumulative costs
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Basic", position=1, cost=10
    )
    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Advanced", position=2, cost=15
    )
    upgrade3 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Master", position=3, cost=20
    )

    assert upgrade1.cost_int() == 10  # Just upgrade1
    assert upgrade2.cost_int() == 25  # upgrade1 + upgrade2
    assert upgrade3.cost_int() == 45  # upgrade1 + upgrade2 + upgrade3


@pytest.mark.django_db
def test_content_equipment_upgrade_cost_int_multi_mode():
    """Test cost_int in MULTI mode returns direct cost."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Gene-smithing",
        category=category,
        upgrade_mode=ContentEquipment.UpgradeMode.MULTI,
    )

    upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Enhanced Reflexes", position=1, cost=30
    )

    assert upgrade.cost_int() == 30


@pytest.mark.django_db
def test_content_equipment_upgrade_cost_display_with_sign():
    """Test cost_display shows sign for upgrades."""
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment",
        category=category,
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
    )
    upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Upgrade", position=1, cost=15
    )
    assert upgrade.cost_display() == "+15¢"


@pytest.mark.django_db
def test_content_equipment_upgrade_cost_display_unsaved():
    """Test cost_display on unsaved upgrade uses direct cost."""
    upgrade = ContentEquipmentUpgrade(name="Test Upgrade", cost=25, position=1)
    assert upgrade.cost_display() == "+25¢"


# ContentFighterEquipmentListItem cost methods tests


@pytest.mark.django_db
def test_content_fighter_equipment_list_item_cost_int():
    """Test cost_int returns the cost."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter", category=FighterCategoryChoices.GANGER, house=house
    )
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category
    )

    list_item = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=equipment, cost=45
    )

    assert list_item.cost_int() == 45


@pytest.mark.django_db
def test_content_fighter_equipment_list_item_cost_display():
    """Test cost_display formats with currency symbol."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter", category=FighterCategoryChoices.GANGER, house=house
    )
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category
    )

    list_item = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=equipment, cost=45
    )

    assert list_item.cost_display() == "45¢"


# ContentFighterEquipmentListWeaponAccessory cost methods tests


@pytest.mark.django_db
def test_content_fighter_equipment_list_weapon_accessory_cost_int():
    """Test cost_int returns the cost."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter", category=FighterCategoryChoices.GANGER, house=house
    )
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory", cost=20
    )

    list_item = ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=fighter, weapon_accessory=accessory, cost=15
    )

    assert list_item.cost_int() == 15


@pytest.mark.django_db
def test_content_fighter_equipment_list_weapon_accessory_cost_display():
    """Test cost_display formats with currency symbol."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter", category=FighterCategoryChoices.GANGER, house=house
    )
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory", cost=20
    )

    list_item = ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=fighter, weapon_accessory=accessory, cost=15
    )

    assert list_item.cost_display() == "15¢"


# ContentFighterEquipmentListUpgrade cost methods tests


@pytest.mark.django_db
def test_content_fighter_equipment_list_upgrade_cost_int():
    """Test cost_int returns the cost."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter", category=FighterCategoryChoices.GANGER, house=house
    )
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category
    )
    upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Test Upgrade", position=1, cost=30
    )

    list_item = ContentFighterEquipmentListUpgrade.objects.create(
        fighter=fighter, upgrade=upgrade, cost=25
    )

    assert list_item.cost_int() == 25


@pytest.mark.django_db
def test_content_fighter_equipment_list_upgrade_cost_display():
    """Test cost_display formats with currency symbol."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter", category=FighterCategoryChoices.GANGER, house=house
    )
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category
    )
    upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Test Upgrade", position=1, cost=30
    )

    list_item = ContentFighterEquipmentListUpgrade.objects.create(
        fighter=fighter, upgrade=upgrade, cost=25
    )

    assert list_item.cost_display() == "25¢"


# ContentFighterDefaultAssignment cost methods tests


@pytest.mark.django_db
def test_content_fighter_default_assignment_cost_int():
    """Test cost_int returns the cost."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter", category=FighterCategoryChoices.GANGER, house=house
    )
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category
    )

    assignment = ContentFighterDefaultAssignment.objects.create(
        fighter=fighter, equipment=equipment, cost=35
    )

    assert assignment.cost_int() == 35


@pytest.mark.django_db
def test_content_fighter_default_assignment_cost_display():
    """Test cost_display formats with currency symbol."""
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter", category=FighterCategoryChoices.GANGER, house=house
    )
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="Gear"
    )
    equipment = ContentEquipment.objects.create(
        name="Test Equipment", category=category
    )

    assignment = ContentFighterDefaultAssignment.objects.create(
        fighter=fighter, equipment=equipment, cost=0
    )

    assert assignment.cost_display() == "0¢"
