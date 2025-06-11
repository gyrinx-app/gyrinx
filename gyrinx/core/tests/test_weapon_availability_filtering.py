import pytest
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
from gyrinx.core.models import List, ListFighter, User
from gyrinx.models import FighterCategoryChoices


@pytest.fixture
def setup_test_data(db):
    """Create test data for availability filtering tests."""
    # Create user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create house
    house = ContentHouse.objects.create(name="Test House")

    # Create fighter type
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category=FighterCategoryChoices.JUVE,
        base_cost=100,
    )

    # Create equipment category
    weapon_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Test Weapons",
        defaults={"group": "Weapons & Ammo"},
    )

    armor_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Test Armor",
        defaults={"group": "Gear"},
    )

    # Create common weapon (should always be visible)
    common_weapon = ContentEquipment.objects.create(
        name="Common Lasgun",
        category=weapon_category,
        rarity="C",
        rarity_roll=None,  # Common items often don't have rarity_roll
    )

    # Create standard profile (cost=0, should always be visible)
    ContentWeaponProfile.objects.create(
        equipment=common_weapon,
        name="",
        cost=0,
        rarity="C",
    )

    # Create rare profile on common weapon (should be visible when no filter)
    ContentWeaponProfile.objects.create(
        equipment=common_weapon,
        name="Hotshot",
        cost=20,
        rarity="R",
        rarity_roll=8,
    )

    # Create rare weapon
    rare_weapon = ContentEquipment.objects.create(
        name="Rare Plasma Gun",
        category=weapon_category,
        rarity="R",
        rarity_roll=10,
    )

    # Create profiles for rare weapon
    ContentWeaponProfile.objects.create(
        equipment=rare_weapon,
        name="",
        cost=0,
        rarity="C",
    )

    ContentWeaponProfile.objects.create(
        equipment=rare_weapon,
        name="Overcharge",
        cost=50,
        rarity="R",
        rarity_roll=12,
    )

    # Create armor items for testing non-weapon filtering
    ContentEquipment.objects.create(
        name="Common Armor",
        category=armor_category,
        rarity="C",
        cost="10",
    )

    ContentEquipment.objects.create(
        name="Rare Armor",
        category=armor_category,
        rarity="R",
        rarity_roll=9,
        cost="50",
    )

    # Add common weapon to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=common_weapon,
    )

    # Add armor items to fighter's equipment list too
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=ContentEquipment.objects.get(name="Common Armor"),
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=ContentEquipment.objects.get(name="Rare Armor"),
    )

    # Create user list and fighter
    user_list = List.objects.create(
        name="Test Gang",
        content_house=house,
        owner=user,
    )

    list_fighter = ListFighter.objects.create(
        list=user_list,
        content_fighter=content_fighter,
        name="Test Fighter",
        owner=user,
    )

    return {
        "user": user,
        "list": user_list,
        "list_fighter": list_fighter,
        "common_weapon": common_weapon,
        "rare_weapon": rare_weapon,
        "content_fighter": content_fighter,
        "armor_category": armor_category,
        "weapon_category": weapon_category,
    }


@pytest.mark.django_db
def test_common_items_visible_with_rarity_threshold(setup_test_data):
    """Test that Common items remain visible when rarity threshold is set."""
    client = Client()
    client.force_login(setup_test_data["user"])

    # Test with rarity threshold that would exclude items without it
    url = reverse(
        "core:list-fighter-weapons-edit",
        args=[
            setup_test_data["list"].id,
            setup_test_data["list_fighter"].id,
        ],
    )

    # Set mal=5 which is lower than rare items' rarity_roll
    response = client.get(url, {"mal": "5", "al": ["C", "R"]})

    assert response.status_code == 200

    # Common weapon should still be visible
    assert "Common Lasgun" in response.content.decode()

    # Rare weapon with rarity_roll=10 should not be visible
    assert "Rare Plasma Gun" not in response.content.decode()


@pytest.mark.django_db
def test_rare_profiles_visible_without_filter(setup_test_data):
    """Test that rare weapon profiles are visible when no mal filter is set and not using equipment list filter."""
    client = Client()
    client.force_login(setup_test_data["user"])

    url = reverse(
        "core:list-fighter-weapons-edit",
        args=[
            setup_test_data["list"].id,
            setup_test_data["list_fighter"].id,
        ],
    )

    # No mal parameter - should show all profiles
    # Use trading-post filter to see all profiles regardless of equipment list
    response = client.get(url, {"al": ["C", "R"], "filter": "trading-post"})

    assert response.status_code == 200
    content = response.content.decode()

    # Check that we can see the rare profile on the common weapon
    assert "Hotshot" in content

    # Also check standard profiles are visible
    assert "Common Lasgun" in content


@pytest.mark.django_db
def test_mal_filter_works_for_profiles(setup_test_data):
    """Test that mal filter correctly filters weapon profiles."""
    client = Client()
    client.force_login(setup_test_data["user"])

    url = reverse(
        "core:list-fighter-weapons-edit",
        args=[
            setup_test_data["list"].id,
            setup_test_data["list_fighter"].id,
        ],
    )

    # Set mal=10 - should show profiles with rarity_roll <= 10
    # Use trading-post filter to see all profiles regardless of equipment list
    response = client.get(
        url, {"mal": "10", "al": ["C", "R"], "filter": "trading-post"}
    )

    assert response.status_code == 200
    content = response.content.decode()

    # Hotshot profile has rarity_roll=8, should be visible
    assert "Hotshot" in content

    # Overcharge profile has rarity_roll=12, should not be visible
    assert "Overcharge" not in content


@pytest.mark.django_db
def test_armor_filtering_unchanged(setup_test_data):
    """Test that non-weapon equipment filtering still works correctly."""
    client = Client()
    client.force_login(setup_test_data["user"])

    url = reverse(
        "core:list-fighter-gear-edit",
        args=[
            setup_test_data["list"].id,
            setup_test_data["list_fighter"].id,
        ],
    )

    # Test without mal - should see both armors
    response = client.get(url, {"al": ["C", "R"]})
    assert response.status_code == 200
    content = response.content.decode()

    assert "Common Armor" in content
    assert "Rare Armor" in content

    # Test with mal=5 - should only see common armor (Rare has rarity_roll=9)
    response = client.get(url, {"mal": "5", "al": ["C", "R"]})
    assert response.status_code == 200
    content = response.content.decode()

    assert "Common Armor" in content
    assert "Rare Armor" not in content


@pytest.mark.django_db
def test_equipment_list_items_always_shown(setup_test_data):
    """Test that items on fighter's equipment list are shown with E rarity."""
    client = Client()
    client.force_login(setup_test_data["user"])

    url = reverse(
        "core:list-fighter-weapons-edit",
        args=[
            setup_test_data["list"].id,
            setup_test_data["list_fighter"].id,
        ],
    )

    # Test with equipment-list filter (default)
    response = client.get(url, {"filter": "equipment-list", "al": ["C", "R"]})

    assert response.status_code == 200

    # Common weapon should be visible as it's on the equipment list
    assert "Common Lasgun" in response.content.decode()
