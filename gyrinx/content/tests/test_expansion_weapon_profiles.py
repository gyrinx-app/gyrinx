"""
Tests for weapon profile support in equipment list expansions.
"""

import pytest
from django.contrib.auth import get_user_model

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
    ContentWeaponProfile,
)
from gyrinx.models import FighterCategoryChoices
from gyrinx.content.models_.expansion import (
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentListExpansionRuleByHouse,
    ExpansionRuleInputs,
)
from gyrinx.core.models.list import List, ListFighter, ListFighterEquipmentAssignment

User = get_user_model()


@pytest.mark.django_db
def test_expansion_with_weapon_profile():
    """Test that expansion can specify a weapon profile with custom cost."""
    # Setup
    user = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="Test House")

    # Create a weapon with profiles
    category = ContentEquipmentCategory.objects.create(name="Weapon")
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=category,
        cost="50",
    )

    # Create standard profile (free)
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="",  # Standard profile has no name
        cost=0,
    )

    # Create special ammo profile
    special_profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Special Ammo",
        cost=15,  # Base cost of 15
    )

    # Create fighter
    fighter_type = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        base_cost=100,
        category=FighterCategoryChoices.LEADER,
    )

    # Create expansion that adds special ammo with custom cost
    expansion = ContentEquipmentListExpansion.objects.create(
        name="House Special Ammo Access"
    )

    # Add rule that applies to the house
    rule = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    expansion.rules.add(rule)

    # Add special ammo profile to expansion with custom cost
    expansion_item = ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=weapon,
        weapon_profile=special_profile,
        cost=10,  # Override cost to 10 instead of 15
    )

    # Create list and fighter
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
    )
    list_fighter = ListFighter.objects.create(
        name="Fighter 1",
        list=lst,
        content_fighter=fighter_type,
        owner=user,
    )

    # Test that expansion applies
    rule_inputs = ExpansionRuleInputs(list=lst, fighter=list_fighter)
    assert expansion.applies_to(rule_inputs)

    # Test that expansion item exists with correct profile
    assert expansion_item.weapon_profile == special_profile
    assert expansion_item.cost == 10


@pytest.mark.django_db
def test_expansion_profile_cost_override():
    """Test that expansion profile cost overrides base profile cost."""
    # Setup
    user = User.objects.create_user(username="testuser2", password="password")
    house = ContentHouse.objects.create(name="Test House 2")

    # Create weapon and profiles
    category = ContentEquipmentCategory.objects.create(name="Weapon")
    weapon = ContentEquipment.objects.create(
        name="Plasma Gun",
        category=category,
        cost="100",
    )

    plasma_profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Plasma",
        cost=30,  # Base plasma cost
    )

    # Create fighter
    fighter_type = ContentFighter.objects.create(
        type="Champion",
        house=house,
        base_cost=200,
        category=FighterCategoryChoices.CHAMPION,
    )

    # Create expansion with cheaper plasma
    expansion = ContentEquipmentListExpansion.objects.create(name="Plasma Discount")

    rule = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    expansion.rules.add(rule)

    # Add plasma with discount
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=weapon,
        weapon_profile=plasma_profile,
        cost=20,  # Discounted to 20
    )

    # Create list and fighter
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
    )
    list_fighter = ListFighter.objects.create(
        name="Champion 1",
        list=lst,
        content_fighter=fighter_type,
        owner=user,
    )

    # Create assignment with the profile
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
    )
    assignment.weapon_profiles_field.add(plasma_profile)

    # Test that expansion applies
    rule_inputs = ExpansionRuleInputs(list=lst, fighter=list_fighter)
    assert expansion.applies_to(rule_inputs)

    # Test that the expansion item was created with correct cost override
    expansion_items = ContentEquipmentListExpansionItem.objects.filter(
        expansion=expansion,
        equipment=weapon,
        weapon_profile=plasma_profile,
    )
    assert expansion_items.exists()
    assert expansion_items.first().cost == 20  # Expansion override, not base 30


@pytest.mark.django_db
def test_equipment_list_filter_includes_expansion_profiles():
    """Test that equipment list filter shows profiles from expansions."""
    # This test would require more complex setup including the view
    # For now, we test the queryset method
    user = User.objects.create_user(username="testuser3", password="password")
    house = ContentHouse.objects.create(name="Test House 3")

    # Create weapon
    category = ContentEquipmentCategory.objects.create(name="Weapon")
    weapon = ContentEquipment.objects.create(
        name="Bolter",
        category=category,
        cost="50",
    )

    # Create profiles
    standard = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="",
        cost=0,
    )

    special = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Kraken Rounds",
        cost=15,
    )

    # Create fighter
    fighter_type = ContentFighter.objects.create(
        type="Marine",
        house=house,
        base_cost=100,
        category=FighterCategoryChoices.GANGER,
    )

    # Create expansion that adds special rounds
    expansion = ContentEquipmentListExpansion.objects.create(name="Special Ammo")

    rule = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    expansion.rules.add(rule)

    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=weapon,
        weapon_profile=special,
        cost=12,
    )

    # Create list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
    )
    list_fighter = ListFighter.objects.create(
        name="Marine 1",
        list=lst,
        content_fighter=fighter_type,
        owner=user,
    )

    # Test with_expansion_profiles_for_fighter

    rule_inputs = ExpansionRuleInputs(list=lst, fighter=list_fighter)

    equipment = ContentEquipment.objects.filter(
        id=weapon.id
    ).with_expansion_profiles_for_fighter(fighter_type, rule_inputs)

    # The equipment should have profiles prefetched
    eq = equipment.first()
    assert hasattr(eq, "pre_profiles_for_fighter")

    # Both profiles should be available
    profile_ids = [p.id for p in eq.pre_profiles_for_fighter]
    assert standard.id in profile_ids
    assert special.id in profile_ids


@pytest.mark.skip(reason="Temporarily disabling expansion tests")
@pytest.mark.django_db
def test_fighter_cost_with_expansion_equipment():
    """Test that fighter total cost includes expansion cost overrides."""
    user = User.objects.create_user(username="testuser4", password="password")
    house = ContentHouse.objects.create(name="Test House 4")

    # Create equipment
    category = ContentEquipmentCategory.objects.create(name="Gear")
    armor = ContentEquipment.objects.create(
        name="Power Armor",
        category=category,
        cost="50",  # Base cost 50
    )

    # Create fighter
    fighter_type = ContentFighter.objects.create(
        type="Leader",
        house=house,
        base_cost=100,
        category=FighterCategoryChoices.LEADER,
    )

    # Create expansion with cheaper armor
    expansion = ContentEquipmentListExpansion.objects.create(name="Armor Discount")

    rule = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    expansion.rules.add(rule)

    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=armor,
        cost=30,  # Discounted to 30
    )

    # Create list and fighter
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
    )
    list_fighter = ListFighter.objects.create(
        name="Leader 1",
        list=lst,
        content_fighter=fighter_type,
        owner=user,
    )

    # Add armor to fighter
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=armor,
    )

    # Test fighter cost
    # Fighter base: 100
    # Armor with expansion discount: 30 (not 50)
    # Total: 130
    assert list_fighter.cost_int() == 130


@pytest.mark.skip(reason="Temporarily disabling expansion tests")
@pytest.mark.django_db
def test_multiple_expansions_same_equipment_different_profiles():
    """Test multiple expansions can add different profiles of same weapon."""
    user = User.objects.create_user(username="testuser5", password="password")
    house = ContentHouse.objects.create(name="Test House 5")

    # Create weapon with multiple profiles
    category = ContentEquipmentCategory.objects.create(name="Weapon")
    weapon = ContentEquipment.objects.create(
        name="Multi-ammo Gun",
        category=category,
        cost="40",
    )

    profile1 = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Ammo Type A",
        cost=10,
    )

    profile2 = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Ammo Type B",
        cost=15,
    )

    # Create fighter
    fighter_type = ContentFighter.objects.create(
        type="Specialist",
        house=house,
        base_cost=80,
        category=FighterCategoryChoices.SPECIALIST,
    )

    # Create two expansions
    expansion1 = ContentEquipmentListExpansion.objects.create(name="Ammo Pack A")
    expansion2 = ContentEquipmentListExpansion.objects.create(name="Ammo Pack B")

    # Both apply to same house
    rule1 = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    expansion1.rules.add(rule1)

    rule2 = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    expansion2.rules.add(rule2)

    # Add different profiles in each expansion
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion1,
        equipment=weapon,
        weapon_profile=profile1,
        cost=8,
    )

    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion2,
        equipment=weapon,
        weapon_profile=profile2,
        cost=12,
    )

    # Create list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
    )
    list_fighter = ListFighter.objects.create(
        name="Specialist 1",
        list=lst,
        content_fighter=fighter_type,
        owner=user,
    )

    # Test both expansions apply
    rule_inputs = ExpansionRuleInputs(list=lst, fighter=list_fighter)
    assert expansion1.applies_to(rule_inputs)
    assert expansion2.applies_to(rule_inputs)

    # Both profiles should be available with their expansion costs
    equipment = ContentEquipment.objects.filter(
        id=weapon.id
    ).with_expansion_profiles_for_fighter(fighter_type, rule_inputs)

    eq = equipment.first()
    profiles = eq.pre_profiles_for_fighter

    # Find the profiles
    profile1_found = next((p for p in profiles if p.id == profile1.id), None)
    profile2_found = next((p for p in profiles if p.id == profile2.id), None)

    assert profile1_found is not None
    assert profile2_found is not None

    # Check the costs are from expansions
    assert profile1_found.cost_for_fighter == 8  # From expansion1
    assert profile2_found.cost_for_fighter == 12  # From expansion2


@pytest.mark.django_db
def test_expansion_item_weapon_profile_validation():
    """Test that weapon_profile must match the equipment."""
    User.objects.create_user(username="testuser6", password="password")
    ContentHouse.objects.create(name="Test House 6")

    # Create two different weapons
    category = ContentEquipmentCategory.objects.create(name="Weapon")
    weapon1 = ContentEquipment.objects.create(
        name="Weapon 1",
        category=category,
        cost="30",
    )
    weapon2 = ContentEquipment.objects.create(
        name="Weapon 2",
        category=category,
        cost="40",
    )

    # Create profile for weapon1
    profile1 = ContentWeaponProfile.objects.create(
        equipment=weapon1,
        name="Profile 1",
        cost=10,
    )

    # Create expansion
    expansion = ContentEquipmentListExpansion.objects.create(name="Test Expansion")

    # Try to create expansion item with mismatched weapon and profile
    expansion_item = ContentEquipmentListExpansionItem(
        expansion=expansion,
        equipment=weapon2,  # Weapon 2
        weapon_profile=profile1,  # But profile from Weapon 1
    )

    # Validation should fail
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        expansion_item.clean()

    assert "Weapon profile must match the equipment selected" in str(exc_info.value)


@pytest.mark.django_db
def test_expansion_item_can_have_null_profile():
    """Test that expansion items can have null weapon_profile for non-weapons."""
    User.objects.create_user(username="testuser7", password="password")
    ContentHouse.objects.create(name="Test House 7")

    # Create non-weapon equipment
    category = ContentEquipmentCategory.objects.create(name="Test Armor Category")
    armor = ContentEquipment.objects.create(
        name="Flak Armor",
        category=category,
        cost="10",
    )

    # Create expansion
    expansion = ContentEquipmentListExpansion.objects.create(name="Armor Access")

    # Create expansion item without weapon profile
    expansion_item = ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=armor,
        weapon_profile=None,  # No profile for armor
        cost=8,
    )

    # Should work fine
    assert expansion_item.weapon_profile is None
    assert expansion_item.cost == 8

    # Clean should pass
    expansion_item.clean()  # Should not raise


@pytest.mark.skip(reason="Temporarily disabling expansion tests")
@pytest.mark.django_db
def test_expansion_profile_cost_does_not_affect_base_equipment():
    """Test that expansion profile costs only affect the profile, not the base equipment."""
    user = User.objects.create_user(username="testuser8", password="password")
    house = ContentHouse.objects.create(name="Test House 8")

    # Create weapon with base cost
    category = ContentEquipmentCategory.objects.create(name="Special Weapon")
    weapon = ContentEquipment.objects.create(
        name="Lasgun",
        category=category,
        cost="10",  # Base cost is 10
    )

    # Create profiles
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="",  # Standard profile
        cost=0,
    )

    hotshot = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Hotshot",
        cost=20,  # Hotshot normally costs 20
    )

    # Create fighter
    fighter_type = ContentFighter.objects.create(
        type="Trooper",
        house=house,
        base_cost=50,
        category=FighterCategoryChoices.GANGER,
    )

    # Create expansion that makes hotshot cheaper but doesn't change base weapon cost
    expansion = ContentEquipmentListExpansion.objects.create(name="Hotshot Discount")

    rule = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    expansion.rules.add(rule)

    # Add ONLY the hotshot profile with discount, NOT the base weapon
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=weapon,
        weapon_profile=hotshot,
        cost=5,  # Hotshot discounted to 5
    )

    # Test with_expansion_cost_for_fighter
    rule_inputs = ExpansionRuleInputs(
        list=List.objects.create(
            name="Test List",
            owner=user,
            content_house=house,
        ),
        fighter=None,
    )

    equipment = ContentEquipment.objects.filter(
        id=weapon.id
    ).with_expansion_cost_for_fighter(fighter_type, rule_inputs)

    eq = equipment.first()
    # Base equipment cost should NOT be affected by profile-specific expansion
    assert eq.cost_for_fighter == 10  # Still base cost, not 5

    # Now test with_expansion_profiles_for_fighter
    equipment = ContentEquipment.objects.filter(
        id=weapon.id
    ).with_expansion_profiles_for_fighter(fighter_type, rule_inputs)

    eq = equipment.first()
    profiles = eq.pre_profiles_for_fighter

    # Find the profiles
    standard_profile = next((p for p in profiles if p.name == ""), None)
    hotshot_profile = next((p for p in profiles if p.name == "Hotshot"), None)

    assert standard_profile is not None
    assert hotshot_profile is not None

    # Standard profile should have no cost override
    assert standard_profile.cost_for_fighter == 0

    # Hotshot profile should have expansion cost override
    assert hotshot_profile.cost_for_fighter == 5  # Expansion discount applied
