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
    # Find the weapon card by looking for the card-header div that contains the weapon name
    # We need to find the actual weapon card, not just the page title
    card_header_start = content.find('class="card-header')
    assert card_header_start > 0, "Should have a card header"

    # Get a chunk of content around the card to check for weapon stats
    weapon_section = content[card_header_start : card_header_start + 3000]

    # Check that the weapon name is in the card header
    assert weapon.name in weapon_section, f"Should have {weapon.name} in the card"

    # Standard profile stats should be visible in the table
    # These will be in table cells
    assert "12" in weapon_section  # range_short
    assert "24" in weapon_section  # range_long
    assert "4" in weapon_section  # strength
    assert "-1" in weapon_section  # armour_piercing
    assert "1" in weapon_section  # damage
    assert "4+" in weapon_section  # ammo

    # The paid profile (Kraken Bolts) should be in the available profiles section
    # It should have an "Add" button since it's not assigned yet
    assert "Kraken Bolts" in content
    # Find the Kraken Bolts section and check for Add button nearby
    kraken_index = content.find("Kraken Bolts")
    assert kraken_index > 0, "Kraken Bolts should be in the page"
    # Need to look further ahead to find the Add button (it's in the HTML after the form elements)
    nearby = content[kraken_index : kraken_index + 1000]
    assert "Add" in nearby or ">Add<" in nearby, (
        "Kraken Bolts should have an Add button"
    )
