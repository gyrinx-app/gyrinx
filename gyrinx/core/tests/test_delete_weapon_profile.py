"""Tests for deleting weapon profiles from equipment assignments."""

import pytest
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentFighterEquipmentListItem
from gyrinx.core.models.list import ListFighterEquipmentAssignment


@pytest.fixture
def client(user):
    """Create a logged-in test client."""
    c = Client()
    c.login(username="testuser", password="password")
    return c


@pytest.mark.django_db
def test_delete_weapon_profile_view_get_without_error(
    client,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
    content_equipment_categories,
):
    """Test that the delete_weapon_profile view loads without AttributeError.

    This is a regression test for issue #1099 where accessing the delete
    weapon profile page caused an AttributeError because the view was
    passing a ContentWeaponProfile instead of a VirtualWeaponProfile to
    profile_cost_int().
    """
    # Create test list and fighter
    test_list = make_list("Test List")
    list_fighter = make_list_fighter(test_list, "Test Fighter")

    # Create a weapon with a profile
    weapon = make_equipment(
        "Test Weapon",
        category=content_equipment_categories[0],
        rarity="C",
        cost="50",
    )

    # Create a weapon profile
    profile = make_weapon_profile(
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

    # Add the profile to the assignment
    assignment.weapon_profiles_field.add(profile)

    # Test accessing the delete page - this was causing AttributeError before the fix
    url = reverse(
        "core:list-fighter-weapon-profile-delete",
        args=[test_list.id, list_fighter.id, assignment.id, profile.id],
    )
    response = client.get(url)

    # The page should load successfully without AttributeError
    assert response.status_code == 200

    # The context should include the profile cost
    assert "profile_cost" in response.context
    assert response.context["profile_cost"] == 10


@pytest.mark.django_db
def test_delete_weapon_profile_post_without_error(
    client,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
    content_equipment_categories,
):
    """Test that deleting a weapon profile via POST works without AttributeError.

    This is a regression test for issue #1099 where submitting the delete
    form caused an AttributeError in the POST handler.
    """
    # Create test list and fighter
    test_list = make_list("Test List")
    list_fighter = make_list_fighter(test_list, "Test Fighter")

    # Create a weapon with a profile
    weapon = make_equipment(
        "Test Weapon",
        category=content_equipment_categories[0],
        rarity="C",
        cost="50",
    )

    # Create a weapon profile
    profile = make_weapon_profile(
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

    # Add the profile to the assignment
    assignment.weapon_profiles_field.add(profile)

    # Verify profile is attached
    assert profile in assignment.weapon_profiles_field.all()

    # Submit the delete form
    url = reverse(
        "core:list-fighter-weapon-profile-delete",
        args=[test_list.id, list_fighter.id, assignment.id, profile.id],
    )
    response = client.post(url)

    # Should redirect successfully
    assert response.status_code == 302

    # Refresh the assignment from database
    assignment.refresh_from_db()

    # Profile should be removed
    assert profile not in assignment.weapon_profiles_field.all()
