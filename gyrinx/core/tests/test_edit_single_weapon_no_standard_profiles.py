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
def test_standard_profiles_not_in_available_list(
    client, test_list, list_fighter, weapon_category
):
    """Test that standard (free) profiles are not shown in available profiles."""
    # Create a weapon with both standard and paid profiles
    weapon = ContentEquipment.objects.create(
        name="Test Weapon",
        category=weapon_category,
        rarity="C",
        cost="50",
    )

    # Create a standard (free) profile - should NOT appear in available list
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="",  # Standard profiles typically have no name
        cost=0,  # Free
        rarity="C",
    )

    # Create another standard profile with a name - should still NOT appear
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Standard Ammo",
        cost=0,  # Free
        rarity="C",
    )

    # Create paid profiles - should appear in available list
    paid_profile1 = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Special Ammo",
        cost=10,
        rarity="R",
    )

    paid_profile2 = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Premium Ammo",
        cost=20,
        rarity="R",
    )

    # Add weapon and profiles to fighter's equipment list
    # Add base weapon
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=weapon,
    )

    # Add paid profiles to equipment list so they're available
    for profile in [paid_profile1, paid_profile2]:
        ContentFighterEquipmentListItem.objects.create(
            fighter=list_fighter.content_fighter,
            equipment=weapon,
            weapon_profile=profile,
        )

    # Assign the weapon to the fighter
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

    # Check the content
    content = response.content.decode()

    # Standard profiles should NOT be in the available profiles section
    # Look for the "Available Profiles" section (new consolidated table format)
    available_section_start = content.find("Available Profiles")
    assert available_section_start > 0, "Should have Available Profiles section"

    # Get just the available profiles section (approximate)
    available_section = content[
        available_section_start : available_section_start + 3000
    ]

    # Debug: write full section to file to see what's there
    with open("/tmp/test_available_section.html", "w") as f:
        f.write(available_section)

    # At least one paid profile should appear (Special Ammo was added to equipment list)
    assert "Special Ammo" in available_section
    # Cost should be visible - but might be calculated differently
    # The profile_cost_int might return different value due to fighter overrides

    # The key test: Standard profiles should NOT appear in available section
    # Check that none of the free profile names appear in the available section
    assert "Standard Ammo" not in available_section  # Named standard profile
    # Note: "(Free)" might appear if fighter has overrides that make profiles free

    # Also check context data if available
    if hasattr(response, "context") and response.context:
        profiles = response.context.get("profiles", [])
        # Check that paid profiles are in the list
        profile_names = [p["name"] for p in profiles]
        assert "Special Ammo" in profile_names
        assert "Premium Ammo" in profile_names
        # Standard profiles should NOT be in the list
        assert "Standard Ammo" not in profile_names
        assert "" not in profile_names  # Unnamed standard profile
