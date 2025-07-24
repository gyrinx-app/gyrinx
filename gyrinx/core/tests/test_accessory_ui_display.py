import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipmentListWeaponAccessory,
    ContentHouse,
    ContentWeaponAccessory,
)
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment

User = get_user_model()


@pytest.mark.django_db
def test_accessory_form_shows_weapon_info_and_tooltip(client):
    """Test that the accessory form shows weapon name, base cost, and tooltip."""
    # Create user and authenticate
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create house
    house = ContentHouse.objects.create(name="Test House")

    # Create weapon category and weapon
    category = ContentEquipmentCategory.objects.create(name="Weapons")
    weapon = ContentEquipment.objects.create(name="Lasgun", category=category, cost=10)

    # Create accessories
    red_dot = ContentWeaponAccessory.objects.create(
        name="Red Dot Sight",
        cost=10,
    )
    master_crafted = ContentWeaponAccessory.objects.create(
        name="Master Crafted",
        cost=0,
        cost_expression="ceil(cost_int * 0.25 / 5) * 5",
    )

    # Create list, fighter, and assignment
    list_obj = List.objects.create(name="Test Gang", owner=user, content_house=house)
    content_fighter = ContentFighter.objects.create(
        type="Ganger", house=house, base_cost=50, category="GANGER"
    )
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        list=list_obj,
        content_fighter=content_fighter,
        owner=user,
    )

    # Add accessories to fighter's equipment list with appropriate costs
    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=content_fighter,
        weapon_accessory=red_dot,
        cost=10,  # Red Dot Sight base cost
    )
    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=content_fighter,
        weapon_accessory=master_crafted,
        cost=0,  # Master Crafted has expression-based cost
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )

    # Make request to the accessory edit page
    url = reverse(
        "core:list-fighter-weapon-accessories-edit",
        args=[list_obj.id, fighter.id, assignment.id],
    )
    response = client.get(url)

    # Check response
    assert response.status_code == 200

    # Check weapon name is displayed
    assert "Lasgun" in response.content.decode()
    assert "<strong>Name:</strong> Lasgun" in response.content.decode()

    # Check weapon details section exists
    assert "Weapon Details" in response.content.decode()

    # Check weapon cost is displayed (10¢)
    assert "10¢" in response.content.decode()

    # Check form shows accessories with correct costs
    # Red Dot Sight should show 10¢
    assert "Red Dot Sight" in response.content.decode()
    assert "10¢" in response.content.decode()
    # Master Crafted should show 5¢ (25% of 10, rounded up to nearest 5)
    assert "Master Crafted" in response.content.decode()
    assert "5¢" in response.content.decode()


@pytest.mark.django_db
def test_accessory_selection_preserves_existing_accessories(client):
    """Test that the form correctly shows which accessories are already selected."""
    # Create user and authenticate
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create house
    house = ContentHouse.objects.create(name="Test House")

    # Create weapon category and weapon
    category = ContentEquipmentCategory.objects.create(name="Weapons")
    weapon = ContentEquipment.objects.create(
        name="Bolt Pistol", category=category, cost=20
    )

    # Create accessories
    accessory1 = ContentWeaponAccessory.objects.create(
        name="Extended Magazine",
        cost=5,
    )
    accessory2 = ContentWeaponAccessory.objects.create(
        name="Custom Grip",
        cost=0,
        cost_expression="cost_int * 0.1",  # 10% of weapon cost
    )

    # Create list, fighter, and assignment with one accessory already added
    list_obj = List.objects.create(name="Test Gang", owner=user, content_house=house)
    content_fighter = ContentFighter.objects.create(
        type="Leader", house=house, base_cost=100, category="LEADER"
    )
    fighter = ListFighter.objects.create(
        name="Test Leader",
        list=list_obj,
        content_fighter=content_fighter,
        owner=user,
    )

    # Add accessories to fighter's equipment list
    # Note: ContentFighterEquipmentListWeaponAccessory can have a cost override
    # We need to set the cost to match the accessory's base cost
    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=content_fighter,
        weapon_accessory=accessory1,
        cost=5,  # Extended Magazine base cost
    )
    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=content_fighter,
        weapon_accessory=accessory2,
        cost=0,  # Custom Grip has expression-based cost
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )
    assignment.weapon_accessories_field.add(accessory1)

    # Make request to the accessory edit page
    url = reverse(
        "core:list-fighter-weapon-accessories-edit",
        args=[list_obj.id, fighter.id, assignment.id],
    )
    response = client.get(url)

    # Check response
    assert response.status_code == 200

    # Check that the form shows the correct selection state
    content = response.content.decode()

    # Check that both accessories are shown
    assert "Extended Magazine" in content
    assert "Custom Grip" in content

    # Check costs are displayed correctly
    # Extended Magazine should show 5¢ (from equipment list)
    assert "Extended Magazine (5¢)" in content
    # Custom Grip should show 2¢ (10% of weapon cost)
    assert "Custom Grip (2¢)" in content

    # Check that Extended Magazine is shown as already added
    # In the new UI, it should appear in the "Current Accessories" section with checkboxes
    # or show "Already Added" badge in the available accessories list
    assert "Current Accessories" in content or "Already Added" in content
