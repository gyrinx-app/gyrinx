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
def test_weapon_edit_shows_standard_profiles(
    client, test_list, list_fighter, weapon_category
):
    """Test that the weapon edit page shows standard profiles as the main statline."""
    # Create a weapon
    weapon = ContentEquipment.objects.create(
        name="Boltgun",
        category=weapon_category,
        rarity="C",
        cost="50",
    )

    # Create a standard (free) profile - this is the main weapon statline
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="",  # Unnamed = main profile
        cost=0,  # Free = standard
        rarity="C",
        # Add some stats to verify they're displayed
        range_short="12",
        range_long="24",
        strength="4",
        armour_piercing="-1",
        damage="1",
        ammo="4+",
    )

    # Create a paid profile
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Kraken Bolts",
        cost=15,
        rarity="R",
        range_short="12",
        range_long="24",
        strength="4",
        armour_piercing="-2",
        damage="1",
        ammo="4+",
    )

    # Add weapon to fighter's equipment list
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

    content = response.content.decode()

    # Debug: save full HTML to see what's rendered
    with open("/tmp/test_weapon_edit_page.html", "w") as f:
        f.write(content)

    # The standard profile should be displayed in the weapon details section
    # Look for the weapon details card - the template now uses "Weapon Profiles" in the header
    weapon_section_start = content.find(f"{weapon.name} - Weapon Profiles")
    assert weapon_section_start > 0, (
        f"Should have weapon details section for {weapon.name}"
    )

    # Get a chunk of content after the weapon name
    weapon_section = content[weapon_section_start : weapon_section_start + 2000]

    # Standard profile stats should be visible
    assert "12" in weapon_section  # range_short
    assert "24" in weapon_section  # range_long
    # The page shows the standard profile is rendered correctly
    # We can see "<em class="text-muted">Standard</em>" label

    # Should show "Standard" label or be unlabeled for the base profile
    assert "Standard" in weapon_section or "<em" in weapon_section

    # The paid profile should NOT be in the assigned profiles yet
    assert "Kraken Bolts" not in weapon_section

    # But it should be in the available profiles section
    available_section_start = content.find("Available Profiles")
    assert available_section_start > 0, "Should have Available Profiles section"
    available_section = content[
        available_section_start : available_section_start + 2000
    ]
    assert "Kraken Bolts" in available_section
