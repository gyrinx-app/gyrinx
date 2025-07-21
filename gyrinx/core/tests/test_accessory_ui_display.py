import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
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
    ContentWeaponAccessory.objects.create(
        name="Red Dot Sight",
        cost=10,
    )
    ContentWeaponAccessory.objects.create(
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
    assert "<strong>Weapon:</strong> Lasgun" in response.content.decode()

    # Check base cost is displayed
    assert "<strong>Base Cost:</strong>" in response.content.decode()
    assert "10¢" in response.content.decode()  # Base cost of lasgun

    # Check tooltip about calculated costs
    assert 'data-bs-toggle="tooltip"' in response.content.decode()
    assert (
        "Some accessories have calculated costs based on the weapon's base cost"
        in response.content.decode()
    )

    # Check form shows accessories with correct costs
    # Red Dot Sight should show 10¢
    assert "Red Dot Sight (10¢)" in response.content.decode()
    # Master Crafted should show 5¢ (25% of 10, rounded up to nearest 5)
    assert "Master Crafted (5¢)" in response.content.decode()


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
    ContentWeaponAccessory.objects.create(
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

    # The form should show checkboxes for accessories
    assert 'type="checkbox"' in content

    # Check that both accessories are shown with correct costs
    assert "Extended Magazine (5¢)" in content
    assert "Custom Grip (2¢)" in content  # 10% of 20

    # Check that the Extended Magazine checkbox is checked
    # Look for checked attribute near the Extended Magazine text
    extended_mag_idx = content.find("Extended Magazine")
    assert extended_mag_idx != -1, "Extended Magazine not found in content"

    # Look for checked within reasonable distance (500 chars before)
    search_start = max(0, extended_mag_idx - 500)
    search_area = content[search_start:extended_mag_idx]
    assert "checked" in search_area, "Extended Magazine checkbox should be checked"
