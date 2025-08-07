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
def test_edit_single_weapon_profile_cost_calculation(
    client, test_list, list_fighter, weapon_category
):
    """Test that the edit_single_weapon view correctly calculates profile costs."""
    # Create a weapon with multiple profiles
    weapon = ContentEquipment.objects.create(
        name="Multi-Profile Weapon",
        category=weapon_category,
        rarity="C",
        cost="50",
    )

    # Create weapon profiles with different costs
    profile1 = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Standard Ammo",
        cost=0,  # Free
        rarity="C",
    )

    profile2 = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Special Ammo",
        cost=15,  # Costs extra
        rarity="R",
    )

    profile3 = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Premium Ammo",
        cost=25,  # Even more expensive
        rarity="R",
    )

    # Add weapon to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=weapon,
    )

    # Assign the weapon to the fighter with one profile
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
    )
    assignment.weapon_profiles_field.add(profile1)

    # Test accessing the edit page for this weapon
    url = reverse(
        "core:list-fighter-weapon-edit",
        args=[test_list.id, list_fighter.id, assignment.id],
    )
    response = client.get(url)

    assert response.status_code == 200

    # Check that the profile_cost_int method works correctly
    from gyrinx.content.models import VirtualWeaponProfile

    virtual_profile1 = VirtualWeaponProfile(profile=profile1)
    virtual_profile2 = VirtualWeaponProfile(profile=profile2)
    virtual_profile3 = VirtualWeaponProfile(profile=profile3)

    assert assignment.profile_cost_int(virtual_profile1) == 0  # Standard ammo is free
    assert assignment.profile_cost_int(virtual_profile2) == 15  # Special ammo costs 15
    assert assignment.profile_cost_int(virtual_profile3) == 25  # Premium ammo costs 25

    # Verify the total weapon profiles cost
    assert assignment.weapon_profiles_cost_int() == 0  # Only has free profile

    # Add a paid profile
    assignment.weapon_profiles_field.add(profile2)
    assignment.refresh_from_db()

    # Clear cached properties after modifying the assignment
    if hasattr(assignment, "_profile_cost_with_override_cached"):
        del assignment._profile_cost_with_override_cached
    if hasattr(assignment, "weapon_profiles_cost_int_cached"):
        del assignment.weapon_profiles_cost_int_cached

    # Now total should include the special ammo cost
    assert assignment.weapon_profiles_cost_int() == 15  # Has special ammo


@pytest.mark.django_db
def test_edit_single_weapon_with_fighter_profile_override(
    client, test_list, list_fighter, weapon_category
):
    """Test profile cost calculation with fighter-specific cost overrides."""
    # Create a weapon with a profile
    weapon = ContentEquipment.objects.create(
        name="Override Test Weapon",
        category=weapon_category,
        rarity="C",
        cost="40",
    )

    profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Override Profile",
        cost=20,  # Default cost
        rarity="R",
    )

    # Add weapon to fighter's equipment list with cost override
    ContentFighterEquipmentListItem.objects.create(
        fighter=list_fighter.content_fighter,
        equipment=weapon,
        weapon_profile=profile,
        cost=10,  # Override cost - cheaper for this fighter
    )

    # Assign the weapon to the fighter
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=weapon,
    )
    assignment.weapon_profiles_field.add(profile)

    # Test that the override cost is used
    from gyrinx.content.models import VirtualWeaponProfile

    virtual_profile = VirtualWeaponProfile(profile=profile)
    assert (
        assignment.profile_cost_int(virtual_profile) == 10
    )  # Uses override, not default 20

    # Test accessing the edit page
    url = reverse(
        "core:list-fighter-weapon-edit",
        args=[test_list.id, list_fighter.id, assignment.id],
    )
    response = client.get(url)

    assert response.status_code == 200
    # Check that the page loads without AttributeError
    assert b"Override Profile" in response.content


@pytest.mark.django_db
def test_edit_single_weapon_available_profiles_display(
    client, test_list, list_fighter, weapon_category
):
    """Test that available profiles are correctly displayed with their costs."""
    # Create a weapon with multiple profiles
    weapon = ContentEquipment.objects.create(
        name="Display Test Weapon",
        category=weapon_category,
        rarity="C",
        cost="30",
    )

    # Create profiles
    free_profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Free Profile",
        cost=0,
        rarity="C",
    )

    paid_profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Paid Profile",
        cost=5,
        rarity="C",
    )

    # Add all profiles to fighter's equipment list
    for profile in [free_profile, paid_profile]:
        ContentFighterEquipmentListItem.objects.create(
            fighter=list_fighter.content_fighter,
            equipment=weapon,
            weapon_profile=profile,
        )

    # Assign weapon without any profiles initially
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

    # Check that profile costs are correctly calculated
    from gyrinx.content.models import VirtualWeaponProfile

    virtual_free_profile = VirtualWeaponProfile(profile=free_profile)
    virtual_paid_profile = VirtualWeaponProfile(profile=paid_profile)

    assert assignment.profile_cost_int(virtual_free_profile) == 0
    assert assignment.profile_cost_int(virtual_paid_profile) == 5

    # Verify the response contains cost information
    content = response.content.decode()
    assert "Free Profile" in content
    assert "Paid Profile" in content
    # The view should show "Free" for 0 cost and "5¢" for paid profile
    assert "Free" in content or "0¢" in content
    assert "5¢" in content
