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
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


@pytest.mark.django_db
def test_can_buy_any_redirects_to_all_filter():
    """Test that when can_buy_any is True, the equipment view redirects to filter=all by default."""
    # Create a user and houses
    user = User.objects.create_user(username="testuser", password="password")

    # Create the Venator house with can_buy_any=True
    venator_house = ContentHouse.objects.create(name="House Venator", can_buy_any=True)

    # Create a fighter for the house
    content_fighter = ContentFighter.objects.create(
        type="Venator Hunt-Champion",
        house=venator_house,
        category=FighterCategoryChoices.CHAMPION,
        base_cost=150,
        movement="5",
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="6+",
        cool="6+",
        willpower="7+",
        intelligence="7+",
    )

    # Create a list and fighter
    venator_list = List.objects.create(
        owner=user,
        name="My Venators",
        content_house=venator_house,
    )

    list_fighter = ListFighter.objects.create(
        list=venator_list,
        content_fighter=content_fighter,
        name="Test Hunt-Champion",
        owner=user,
    )

    # Login and test gear edit page
    client = Client()
    client.login(username="testuser", password="password")

    # Access the gear edit page without filter parameter
    url = reverse(
        "core:list-fighter-gear-edit", args=[venator_list.id, list_fighter.id]
    )
    response = client.get(url)

    # Should redirect to filter=all
    assert response.status_code == 302
    assert response.url == f"{url}?filter=all"

    # Test weapons edit page too
    url = reverse(
        "core:list-fighter-weapons-edit", args=[venator_list.id, list_fighter.id]
    )
    response = client.get(url)

    # Should redirect to filter=all
    assert response.status_code == 302
    assert response.url == f"{url}?filter=all"


@pytest.mark.django_db
def test_can_buy_any_includes_equipment_list_items_with_all_filter():
    """Test that when can_buy_any is True and filter=all, both Trading Post and equipment list items are shown."""
    # Create a user and houses
    user = User.objects.create_user(username="testuser2", password="password")

    # Create the Venator house with can_buy_any=True
    venator_house = ContentHouse.objects.create(name="House Venator", can_buy_any=True)

    # Create equipment categories
    weapon_category = ContentEquipmentCategory.objects.create(
        name="Venator Test Weapons",
        group="Weapon",
    )
    gear_category = ContentEquipmentCategory.objects.create(
        name="Venator Test Gear",
        group="Gear",
    )

    # Create Trading Post equipment (available to all)
    trading_post_weapon = ContentEquipment.objects.create(
        name="Autogun",
        category=weapon_category,
        rarity="C",
        cost="15",
    )
    # Add weapon profile to make it a weapon
    ContentWeaponProfile.objects.create(
        equipment=trading_post_weapon,
        name="",
        cost=15,
    )

    ContentEquipment.objects.create(
        name="Mesh Armour",
        category=gear_category,
        rarity="C",
        cost="15",
    )

    # Create equipment list only items (Venator exclusive)
    venator_weapon = ContentEquipment.objects.create(
        name="Venator Harpoon Launcher",
        category=weapon_category,
        rarity="R",
        cost="110",
    )
    # Add weapon profile to make it a weapon
    ContentWeaponProfile.objects.create(
        equipment=venator_weapon,
        name="",
        cost=110,
    )

    venator_gear = ContentEquipment.objects.create(
        name="Cameleoline Cloak",
        category=gear_category,
        rarity="R",
        cost="40",
    )

    # Create a fighter
    content_fighter = ContentFighter.objects.create(
        type="Venator Hunt-Champion",
        house=venator_house,
        category=FighterCategoryChoices.CHAMPION,
        base_cost=150,
        movement="5",
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="6+",
        cool="6+",
        willpower="7+",
        intelligence="7+",
    )

    # Add equipment list items to the fighter
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=venator_weapon,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=venator_gear,
    )

    # Create a list and fighter
    venator_list = List.objects.create(
        owner=user,
        name="My Venators",
        content_house=venator_house,
    )

    list_fighter = ListFighter.objects.create(
        list=venator_list,
        content_fighter=content_fighter,
        name="Test Hunt-Champion",
        owner=user,
    )

    # Login
    client = Client()
    client.login(username="testuser2", password="password")

    # Test weapons page with filter=all
    url = reverse(
        "core:list-fighter-weapons-edit", args=[venator_list.id, list_fighter.id]
    )
    response = client.get(url, {"filter": "all", "al": ["C", "R"]})

    assert response.status_code == 200
    content = response.content.decode()

    # Both Trading Post and equipment list weapons should be visible
    assert "Autogun" in content
    assert "Venator Harpoon Launcher" in content

    # Test gear page with filter=all
    url = reverse(
        "core:list-fighter-gear-edit", args=[venator_list.id, list_fighter.id]
    )
    response = client.get(url, {"filter": "all", "al": ["C", "R"]})

    assert response.status_code == 200
    content = response.content.decode()

    # Both Trading Post and equipment list gear should be visible
    assert "Mesh Armour" in content
    assert "Cameleoline Cloak" in content


@pytest.mark.django_db
def test_normal_house_defaults_to_equipment_list():
    """Test that normal houses (can_buy_any=False) still default to equipment list filter."""
    # Create a user and houses
    user = User.objects.create_user(username="testuser3", password="password")

    # Create a normal house without can_buy_any
    normal_house = ContentHouse.objects.create(name="House Goliath", can_buy_any=False)

    # Create a fighter
    content_fighter = ContentFighter.objects.create(
        type="Goliath Champion",
        house=normal_house,
        category=FighterCategoryChoices.CHAMPION,
        base_cost=150,
        movement="4",
        weapon_skill="3+",
        ballistic_skill="4+",
        strength="4",
        toughness="4",
        wounds="2",
        initiative="4+",
        attacks="2",
        leadership="6+",
        cool="6+",
        willpower="8+",
        intelligence="8+",
    )

    # Create a list and fighter
    normal_list = List.objects.create(
        owner=user,
        name="My Goliaths",
        content_house=normal_house,
    )

    list_fighter = ListFighter.objects.create(
        list=normal_list,
        content_fighter=content_fighter,
        name="Test Champion",
        owner=user,
    )

    # Login
    client = Client()
    client.login(username="testuser3", password="password")

    # Access the gear edit page without filter parameter
    url = reverse("core:list-fighter-gear-edit", args=[normal_list.id, list_fighter.id])
    response = client.get(url)

    # Should not redirect - stays on equipment list filter
    assert response.status_code == 200
    assert response.context["is_equipment_list"] is True


@pytest.mark.django_db
def test_can_buy_any_no_duplicates_in_equipment_list():
    """Test that equipment appears only once when it's in both Trading Post and equipment list."""
    # Create a user and houses
    user = User.objects.create_user(username="testuser4", password="password")

    # Create the Venator house with can_buy_any=True
    venator_house = ContentHouse.objects.create(name="House Venator", can_buy_any=True)

    # Create equipment category
    weapon_category = ContentEquipmentCategory.objects.create(
        name="Venator Duplicate Test Weapons",
        group="Weapon",
    )

    # Create a weapon that's both in Trading Post and equipment list
    shared_weapon = ContentEquipment.objects.create(
        name="Lasgun",
        category=weapon_category,
        rarity="C",
        cost="10",
    )
    # Add weapon profile to make it a weapon
    ContentWeaponProfile.objects.create(
        equipment=shared_weapon,
        name="",
        cost=10,
    )

    # Create a fighter
    content_fighter = ContentFighter.objects.create(
        type="Venator Hunter",
        house=venator_house,
        category=FighterCategoryChoices.GANGER,
        base_cost=70,
        movement="5",
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="8+",
        intelligence="8+",
    )

    # Add the same weapon to equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=shared_weapon,
    )

    # Create a list and fighter
    venator_list = List.objects.create(
        owner=user,
        name="My Venators",
        content_house=venator_house,
    )

    list_fighter = ListFighter.objects.create(
        list=venator_list,
        content_fighter=content_fighter,
        name="Test Hunter",
        owner=user,
    )

    # Login
    client = Client()
    client.login(username="testuser4", password="password")

    # Test weapons page with filter=all
    url = reverse(
        "core:list-fighter-weapons-edit", args=[venator_list.id, list_fighter.id]
    )
    response = client.get(url, {"filter": "all", "al": ["C", "R"]})

    assert response.status_code == 200

    # Check that the equipment queryset doesn't have duplicates
    equipment = response.context["equipment"]
    equipment_names = [e.name for e in equipment]

    # Lasgun should appear exactly once
    assert equipment_names.count("Lasgun") == 1


@pytest.mark.django_db
def test_can_buy_any_explicit_filter_parameter():
    """Test that explicit filter parameter is respected even with can_buy_any=True."""
    # Create a user and houses
    user = User.objects.create_user(username="testuser5", password="password")

    # Create the Venator house with can_buy_any=True
    venator_house = ContentHouse.objects.create(name="House Venator", can_buy_any=True)

    # Create equipment categories
    weapon_category = ContentEquipmentCategory.objects.create(
        name="Venator Explicit Test Weapons",
        group="Weapon",
    )

    # Create Trading Post equipment
    trading_post_weapon = ContentEquipment.objects.create(
        name="Stub Gun",
        category=weapon_category,
        rarity="C",
        cost="5",
    )
    # Add weapon profile to make it a weapon
    ContentWeaponProfile.objects.create(
        equipment=trading_post_weapon,
        name="",
        cost=5,
    )

    # Create equipment list only item
    venator_weapon = ContentEquipment.objects.create(
        name="Venator Pattern Bolter",
        category=weapon_category,
        rarity="R",
        cost="100",
    )
    # Add weapon profile to make it a weapon
    ContentWeaponProfile.objects.create(
        equipment=venator_weapon,
        name="",
        cost=100,
    )

    # Create a fighter
    content_fighter = ContentFighter.objects.create(
        type="Venator Hunter",
        house=venator_house,
        category=FighterCategoryChoices.GANGER,
        base_cost=70,
        movement="5",
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="8+",
        intelligence="8+",
    )

    # Add equipment list item
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=venator_weapon,
    )

    # Create a list and fighter
    venator_list = List.objects.create(
        owner=user,
        name="My Venators",
        content_house=venator_house,
    )

    list_fighter = ListFighter.objects.create(
        list=venator_list,
        content_fighter=content_fighter,
        name="Test Hunter",
        owner=user,
    )

    # Login
    client = Client()
    client.login(username="testuser5", password="password")

    # Test with explicit filter=equipment-list
    url = reverse(
        "core:list-fighter-weapons-edit", args=[venator_list.id, list_fighter.id]
    )
    response = client.get(url, {"filter": "equipment-list"})

    assert response.status_code == 200
    content = response.content.decode()

    # Only equipment list item should be visible
    assert "Venator Pattern Bolter" in content
    assert "Stub Gun" not in content
    assert response.context["is_equipment_list"] is True

    # Test with explicit filter=all
    response = client.get(url, {"filter": "all", "al": ["C", "R"]})

    assert response.status_code == 200
    content = response.content.decode()

    # Both should be visible
    assert "Venator Pattern Bolter" in content
    assert "Stub Gun" in content
    assert response.context["is_equipment_list"] is False
