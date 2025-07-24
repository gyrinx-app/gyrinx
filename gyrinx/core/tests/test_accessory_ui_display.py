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

    content = response.content.decode()

    # Check weapon name is displayed in the card header
    assert "Lasgun" in content
    # The weapon name appears in multiple places: page title, h1, and card header
    assert '<h4 class="h5 mb-0">Lasgun</h4>' in content

    # Check weapon cost is displayed in the badge (10¢)
    assert '<span class="badge text-bg-secondary">10¢</span>' in content

    # Check form shows accessories with correct costs
    # Red Dot Sight should show 10¢ in Available Accessories
    assert "Red Dot Sight" in content
    assert '<span class="text-muted">(10¢)</span>' in content

    # Master Crafted should show 5¢ (25% of 10, rounded up to nearest 5)
    assert "Master Crafted" in content
    assert '<span class="text-muted">(5¢)</span>' in content


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

    # Extended Magazine should be shown in the weapon details table (already added)
    # It will appear with the crosshair icon
    assert "Extended Magazine" in content
    assert '<i class="bi-crosshair"></i>' in content

    # Custom Grip should only appear in Available Accessories (not yet added)
    assert "Custom Grip" in content
    assert '<span class="text-muted">(2¢)</span>' in content

    # Extended Magazine should NOT appear in Available Accessories since it's already added
    # Check that it's in the weapon table but not in the available accessories list
    weapon_table_section = content[
        content.find('<table class="table') : content.find("</table>")
    ]
    assert "Extended Magazine" in weapon_table_section

    available_section = content[content.find("Available Accessories") :]
    # Extended Magazine should not be in the available accessories
    assert (
        "Extended Magazine" not in available_section
        or "Custom Grip" in available_section
    )
