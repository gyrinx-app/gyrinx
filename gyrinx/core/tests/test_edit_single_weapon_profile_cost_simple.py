import pytest
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighterEquipmentListItem,
    ContentWeaponProfile,
    VirtualWeaponProfile,
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
def test_edit_single_weapon_view_loads_without_error(
    client, test_list, list_fighter, weapon_category
):
    """Test that the edit_single_weapon view loads without AttributeError."""
    # Create a weapon with a profile
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=weapon_category,
        rarity="C",
        cost="50",
    )

    # Create a weapon profile
    profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Test Profile",
        cost=10,
        rarity="C",
    )

    # Add weapon to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=weapon,
    )

    # Assign the weapon to the fighter
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
    )

    # Test accessing the edit page - this was causing AttributeError before the fix
    url = reverse(
        "core:list-fighter-weapon-edit",
        args=[test_list.id, list_fighter.id, assignment.id],
    )
    response = client.get(url)

    # The page should load successfully without AttributeError
    assert response.status_code == 200

    # Check that the profile_cost_int method works with VirtualWeaponProfile
    virtual_profile = VirtualWeaponProfile(profile=profile)
    cost = assignment.profile_cost_int(virtual_profile)
    assert isinstance(cost, int)  # Should return an integer
    assert cost == 10  # Should be the profile's cost
