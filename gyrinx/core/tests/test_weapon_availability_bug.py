"""
Test for weapon availability filtering bug fix.

Bug: Weapons without an availability level (common/on fighter's list) are still 
not appearing when an availability level has been specified.
"""

import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
    ContentWeaponProfile,
)
from gyrinx.core.models.list import List, ListFighter

User = get_user_model()


@pytest.mark.django_db
def test_weapon_availability_filtering_bug_fix():
    """
    Test that weapons with profiles that have no availability level
    are shown when maximum availability level filter is applied.
    
    This reproduces the original bug where weapons were filtered out
    at the equipment level based on their base rarity_roll, preventing
    access to weapon profiles that should be available.
    """
    # Setup test data
    user = User.objects.create_user(username="testuser", password="testpass")
    client = Client()
    client.login(username="testuser", password="testpass")
    
    # Create house and fighter
    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        name="Test Fighter",
        house=house,
        category="GANGER",
        cost=50,
    )
    
    # Create weapon category
    weapon_category = ContentEquipmentCategory.objects.get_or_create(
        name="Basic Weapons",
        defaults={"group": "weapons"}
    )[0]
    
    # Create a weapon that has a high rarity_roll at equipment level
    # but should still be available for its profiles
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=weapon_category,
        cost=100,
        rarity="R",  # Rare weapon
        rarity_roll=20,  # High availability level at equipment level
    )
    
    # Create standard profile (should always be available)
    standard_profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="",  # Standard profile
        cost=0,
        rarity="R",
        rarity_roll=None,  # No availability level
        range_short="8\"",
        range_long="24\"",
        strength="3",
        damage="1",
    )
    
    # Create special ammo profile with low availability requirement
    special_ammo_profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="special ammo",
        cost=20,
        rarity="R",
        rarity_roll=10,  # Lower than weapon's base rarity_roll
        range_short="8\"", 
        range_long="24\"",
        strength="4",
        damage="2",
    )
    
    # Create list and fighter
    lst = List.objects.create(
        name="Test List",
        house=house,
        owner=user,
    )
    
    list_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        name="Test Fighter",
        content_fighter=content_fighter,
    )
    
    # Test the view with availability level filter set to 15
    # The weapon has rarity_roll=20 but its profiles should still be available
    url = reverse('core:list-fighter-weapons-edit', args=[lst.id, list_fighter.id])
    response = client.get(url, {
        'filter': 'all',  # Show all weapons, not just equipment list
        'al': ['R'],  # Show Rare only
        'mal': '15',  # Maximum availability level 15 (less than weapon's 20)
    })
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # The weapon should appear because its profiles are filtered separately
    # and the special ammo profile has rarity_roll=10 <= 15
    assert "Test Weapon" in content, "Weapon should be visible despite high base rarity_roll"
    assert "special ammo" in content, "Special ammo profile should be visible (rarity_roll=10 <= 15)"
    
    # Test with even lower availability level that excludes the special ammo
    response = client.get(url, {
        'filter': 'all',
        'al': ['R'],
        'mal': '5',  # Lower than special ammo's rarity_roll=10
    })
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # The weapon should still appear because it has the standard profile
    # which has no availability requirement (rarity_roll=None)
    assert "Test Weapon" in content, "Weapon should still be visible for standard profile"
    # But special ammo should be filtered out
    assert "special ammo" not in content, "Special ammo should be filtered out (rarity_roll=10 > 5)"


@pytest.mark.django_db  
def test_non_weapon_equipment_still_filtered_by_availability():
    """
    Test that non-weapon equipment is still properly filtered by availability level.
    The fix should only affect weapons, not other equipment.
    """
    # Setup test data
    user = User.objects.create_user(username="testuser2", password="testpass")
    client = Client()
    client.login(username="testuser2", password="testpass")
    
    # Create house and fighter
    house = ContentHouse.objects.create(name="Test House 2")
    content_fighter = ContentFighter.objects.create(
        name="Test Fighter 2",
        house=house,
        category="GANGER",
        cost=50,
    )
    
    # Create armor category (non-weapon)
    armor_category = ContentEquipmentCategory.objects.get_or_create(
        name="Armor",
        defaults={"group": "armor"}
    )[0]
    
    # Create armor with high availability level
    high_availability_armor = ContentEquipment.objects.create(
        name="Rare Armor",
        category=armor_category,
        cost=200,
        rarity="R",
        rarity_roll=20,  # High availability level
    )
    
    # Create armor with low availability level
    low_availability_armor = ContentEquipment.objects.create(
        name="Common Armor",
        category=armor_category,
        cost=50,
        rarity="R",
        rarity_roll=5,  # Low availability level
    )
    
    # Create list and fighter
    lst = List.objects.create(
        name="Test List 2",
        house=house,
        owner=user,
    )
    
    list_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        name="Test Fighter 2", 
        content_fighter=content_fighter,
    )
    
    # Test armor filtering with availability level 10
    url = reverse('core:list-fighter-gear-edit', args=[lst.id, list_fighter.id])
    response = client.get(url, {
        'filter': 'all',
        'al': ['R'],
        'mal': '10',  # Should include low_availability_armor but exclude high_availability_armor
    })
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # Low availability armor should be included (rarity_roll=5 <= 10)
    assert "Common Armor" in content, "Low availability armor should be visible"
    
    # High availability armor should be excluded (rarity_roll=20 > 10)
    assert "Rare Armor" not in content, "High availability armor should be filtered out"