import pytest
from bs4 import BeautifulSoup
from django.urls import reverse

from n23.content.models import (
    ContentEquipment,
    ContentFighterEquipmentListItem,
    ContentWeaponProfile,
)
from n23.core.models.list import ListFighterEquipmentAssignment


@pytest.fixture
def test_list(make_list):
    """Create a test list."""
    return make_list("Test List")


@pytest.fixture
def list_fighter(test_list, make_list_fighter):
    """Create a test list fighter."""
    return make_list_fighter(test_list, "Test Fighter")


@pytest.mark.django_db
def test_standard_profiles_not_in_available_list(
    logged_in_client, test_list, list_fighter, weapon_category
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
    response = logged_in_client.get(url)

    assert response.status_code == 200

    paid_ids = {paid_profile1.id, paid_profile2.id}
    assert {profile["id"] for profile in response.context["profiles"]} == paid_ids

    # The available-profile forms must offer exactly the paid profiles; free
    # profiles may still appear elsewhere as the weapon's standard stats.
    soup = BeautifulSoup(response.content, "html.parser")
    add_inputs = soup.select('form input[name="profile_id"]')
    assert {field["value"] for field in add_inputs} == {
        str(profile_id) for profile_id in paid_ids
    }
    for field in add_inputs:
        button = field.find_parent("form").find("button", type="submit")
        assert button.get_text(strip=True) == "Add"
