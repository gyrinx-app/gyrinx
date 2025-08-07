import pytest
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighterEquipmentListItem,
    ContentWeaponProfile,
)
from gyrinx.core.models.list import ListFighterEquipmentAssignment


@pytest.fixture
def weapon_category():
    """Get or create test weapon category."""
    return ContentEquipmentCategory.objects.get_or_create(
        name="Basic Weapons",
        defaults={"group": "Weapons & Ammo"},
    )[0]


@pytest.fixture
def test_list(make_list):
    """Create a test list."""
    return make_list("Test List")


@pytest.fixture
def list_fighter(test_list, make_list_fighter):
    """Create a test list fighter."""
    return make_list_fighter(test_list, "Test Fighter")


@pytest.fixture
def client(user):
    """Create a logged-in test client."""
    c = Client()
    c.login(username="testuser", password="password")
    return c


@pytest.mark.django_db
def test_no_standard_profiles_in_available_list(
    client, test_list, list_fighter, weapon_category
):
    """Test that standard (cost=0) profiles don't appear in available profiles."""
    # Create a weapon
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=weapon_category,
        rarity="C",
        cost="50",
    )

    # Create a standard (free) profile - should NOT appear
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Standard Profile",
        cost=0,  # Free = standard
        rarity="C",
    )

    # Create a paid profile - should appear
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Paid Profile",
        cost=15,
        rarity="R",
    )

    # Add to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=weapon,
    )

    # Assign weapon to fighter
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
    )

    # Access the edit page
    url = reverse(
        "core:list-fighter-weapon-edit",
        args=[test_list.id, list_fighter.id, assignment.id],
    )
    response = client.get(url)

    assert response.status_code == 200

    # Check context data
    profiles = response.context["profiles"]
    profile_names = [p["name"] for p in profiles]

    # Standard profile should NOT be in the list
    assert "Standard Profile" not in profile_names

    # Only paid profile should be available
    assert "Paid Profile" in profile_names
    assert len(profiles) == 1
