import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipmentListItem,
    ContentHouse,
    ContentWeaponProfile,
)
from gyrinx.core.models.list import List, ListFighter

User = get_user_model()


@pytest.mark.django_db
def test_weapon_profiles_filtered_with_equipment_list():
    """Test that weapon profiles are filtered when equipment list filter is active"""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House", generic=True)

    # Create equipment category for weapons
    weapon_category = ContentEquipmentCategory.objects.create(name="Basic Weapons")

    # Create a weapon
    weapon = ContentEquipment.objects.create(
        name="Test Gun", category=weapon_category, cost=10, rarity="C"
    )

    # Create weapon profiles (ammo types)
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Standard Ammo",
        cost=0,  # Standard profile
        rarity="C",
    )

    special_profile_on_list = ContentWeaponProfile.objects.create(
        equipment=weapon, name="Special Ammo On List", cost=10, rarity="R"
    )

    ContentWeaponProfile.objects.create(
        equipment=weapon, name="Special Ammo Not On List", cost=15, rarity="R"
    )

    # Create a fighter type
    fighter_type = ContentFighter.objects.create(
        house=house,
        type="Test Fighter",
        category="GANGER",
        cost=50,
        movement=4,
        weapon_skill=4,
        ballistic_skill=4,
        strength=3,
        toughness=3,
        wounds=1,
        initiative=4,
        attacks=1,
        leadership=7,
        cool=7,
        willpower=7,
        intelligence=7,
    )

    # Add weapon to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter_type,
        equipment=weapon,
        weapon_profile=None,  # Base weapon
    )

    # Add only one special profile to the equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter_type, equipment=weapon, weapon_profile=special_profile_on_list
    )

    # Note: special_profile_not_on_list is NOT added to the equipment list

    # Create list and fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)

    list_fighter = ListFighter.objects.create(
        name="Test Fighter", content_fighter=fighter_type, list=lst, owner=user
    )

    # Login
    client = Client()
    client.login(username="testuser", password="testpass")

    # Test with equipment list filter active (default)
    response = client.get(
        reverse("core:list-fighter-weapons-edit", args=[lst.id, list_fighter.id])
    )

    assert response.status_code == 200

    # Check that the correct profiles are in the assigns
    assigns = response.context["assigns"]
    weapon_assign = None
    for assign in assigns:
        if assign.equipment.id == weapon.id:
            weapon_assign = assign
            break

    assert weapon_assign is not None, "Weapon should be in assigns"

    profile_names = [p.name for p in weapon_assign.profiles]

    # Standard ammo should always be visible
    assert "Standard Ammo" in profile_names

    # Special ammo on list should be visible
    assert "Special Ammo On List" in profile_names

    # Special ammo NOT on list should NOT be visible
    assert "Special Ammo Not On List" not in profile_names

    # Test with equipment list filter disabled (using trading post filter)
    response = client.get(
        reverse("core:list-fighter-weapons-edit", args=[lst.id, list_fighter.id]),
        {"filter": "trading-post"},
    )

    assert response.status_code == 200

    # Check profiles again
    assigns = response.context["assigns"]
    weapon_assign = None
    for assign in assigns:
        if assign.equipment.id == weapon.id:
            weapon_assign = assign
            break

    assert weapon_assign is not None

    profile_names = [p.name for p in weapon_assign.profiles]

    # All profiles should be visible when not using equipment list filter
    assert "Standard Ammo" in profile_names
    assert "Special Ammo On List" in profile_names
    assert "Special Ammo Not On List" in profile_names

