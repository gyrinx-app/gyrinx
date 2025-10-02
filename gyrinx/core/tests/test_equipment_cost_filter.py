"""Test equipment cost filtering on fighter equipment screens."""

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
def setup_cost_filter_data(db):
    """Create test data for cost filter tests."""
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

    # Create equipment categories
    weapon_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Test Weapons",
        defaults={"group": "Weapons & Ammo"},
    )

    gear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Test Gear",
        defaults={"group": "Gear"},
    )

    # Create weapons with different costs
    cheap_weapon = ContentEquipment.objects.create(
        name="Cheap Weapon",
        category=weapon_category,
        rarity="C",
        cost=10,
    )
    ContentWeaponProfile.objects.create(
        equipment=cheap_weapon,
        name="",
        cost=0,
        rarity="C",
    )

    mid_weapon = ContentEquipment.objects.create(
        name="Mid-priced Weapon",
        category=weapon_category,
        rarity="C",
        cost=50,
    )
    ContentWeaponProfile.objects.create(
        equipment=mid_weapon,
        name="",
        cost=0,
        rarity="C",
    )

    expensive_weapon = ContentEquipment.objects.create(
        name="Expensive Weapon",
        category=weapon_category,
        rarity="C",
        cost=150,
    )
    ContentWeaponProfile.objects.create(
        equipment=expensive_weapon,
        name="",
        cost=0,
        rarity="C",
    )

    # Create gear with different costs
    cheap_gear = ContentEquipment.objects.create(
        name="Cheap Gear",
        category=gear_category,
        rarity="C",
        cost=5,
    )

    mid_gear = ContentEquipment.objects.create(
        name="Mid-priced Gear",
        category=gear_category,
        rarity="C",
        cost=30,
    )

    expensive_gear = ContentEquipment.objects.create(
        name="Expensive Gear",
        category=gear_category,
        rarity="C",
        cost=200,
    )

    # Add all equipment to the fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=cheap_weapon
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=mid_weapon
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=expensive_weapon
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=cheap_gear
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=mid_gear
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=expensive_gear
    )

    # Create list and fighter
    lst = List.objects.create(name="Test List", content_house=house, owner=user)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter, owner=user
    )

    return {
        "user": user,
        "list": lst,
        "fighter": fighter,
        "cheap_weapon": cheap_weapon,
        "mid_weapon": mid_weapon,
        "expensive_weapon": expensive_weapon,
        "cheap_gear": cheap_gear,
        "mid_gear": mid_gear,
        "expensive_gear": expensive_gear,
    }


@pytest.mark.django_db
def test_weapon_cost_filter_no_filter(setup_cost_filter_data):
    """Test that without cost filter, all weapons are shown."""
    data = setup_cost_filter_data
    client = Client()
    client.force_login(data["user"])

    url = reverse(
        "core:list-fighter-weapons-edit",
        args=(data["list"].id, data["fighter"].id),
    )

    response = client.get(url)
    assert response.status_code == 200

    content = response.content.decode()
    # Write to file for debugging
    with open("/tmp/test_output.html", "w") as f:
        f.write(content)

    # Check if we have equipment at all
    has_equipment_section = "Test Weapons" in content or "equipment" in content.lower()

    assert "Cheap Weapon" in content, (
        f"Equipment section present: {has_equipment_section}, response length: {len(content)}"
    )
    assert "Mid-priced Weapon" in content
    assert "Expensive Weapon" in content


@pytest.mark.django_db
def test_weapon_cost_filter_with_max_cost(setup_cost_filter_data):
    """Test that weapons above max cost are filtered out in equipment-list mode (default)."""
    data = setup_cost_filter_data
    client = Client()
    client.force_login(data["user"])

    url = reverse(
        "core:list-fighter-weapons-edit",
        args=(data["list"].id, data["fighter"].id),
    )

    # Filter to show only weapons costing 50 or less (default equipment-list mode)
    response = client.get(url, {"mc": "50"})
    assert response.status_code == 200

    content = response.content.decode()
    assert "Cheap Weapon" in content, (
        "Cheap weapon (cost 10) should be visible with mc=50"
    )
    assert "Mid-priced Weapon" in content, (
        "Mid-priced weapon (cost 50) should be visible with mc=50"
    )
    assert "Expensive Weapon" not in content, (
        "Expensive weapon (cost 150) should NOT be visible with mc=50"
    )


@pytest.mark.django_db
def test_weapon_cost_filter_with_low_max_cost(setup_cost_filter_data):
    """Test that only the cheapest weapon is shown with very low max cost."""
    data = setup_cost_filter_data
    client = Client()
    client.force_login(data["user"])

    url = reverse(
        "core:list-fighter-weapons-edit",
        args=(data["list"].id, data["fighter"].id),
    )

    # Filter to show only weapons costing 10 or less
    response = client.get(url, {"mc": "10"})
    assert response.status_code == 200

    content = response.content.decode()
    assert "Cheap Weapon" in content
    assert "Mid-priced Weapon" not in content
    assert "Expensive Weapon" not in content


@pytest.mark.django_db
def test_gear_cost_filter_no_filter(setup_cost_filter_data):
    """Test that without cost filter, all gear is shown."""
    data = setup_cost_filter_data
    client = Client()
    client.force_login(data["user"])

    url = reverse(
        "core:list-fighter-gear-edit",
        args=(data["list"].id, data["fighter"].id),
    )

    response = client.get(url)
    assert response.status_code == 200

    content = response.content.decode()
    assert "Cheap Gear" in content
    assert "Mid-priced Gear" in content
    assert "Expensive Gear" in content


@pytest.mark.django_db
def test_gear_cost_filter_with_max_cost(setup_cost_filter_data):
    """Test that gear above max cost are filtered out."""
    data = setup_cost_filter_data
    client = Client()
    client.force_login(data["user"])

    url = reverse(
        "core:list-fighter-gear-edit",
        args=(data["list"].id, data["fighter"].id),
    )

    # Filter to show only gear costing 30 or less
    response = client.get(url, {"mc": "30"})
    assert response.status_code == 200

    content = response.content.decode()
    assert "Cheap Gear" in content
    assert "Mid-priced Gear" in content
    assert "Expensive Gear" not in content


@pytest.mark.django_db
def test_cost_filter_preserves_mc_parameter_on_assignment(setup_cost_filter_data):
    """Test that the mc parameter is preserved when adding equipment."""
    data = setup_cost_filter_data
    client = Client()
    client.force_login(data["user"])

    url = reverse(
        "core:list-fighter-gear-edit",
        args=(data["list"].id, data["fighter"].id),
    )

    # Add gear with cost filter active
    response = client.post(
        url,
        {
            "action": "add",
            "content_equipment_id": data["cheap_gear"].id,
            "mc": "30",
        },
    )

    # Should redirect back with mc parameter preserved
    assert response.status_code == 302
    assert "mc=30" in response.url
