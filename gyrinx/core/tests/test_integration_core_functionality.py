"""
Integration tests for core functionality using Django test client.

These tests verify complete user workflows through the UI, ensuring
that all components work together correctly.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentHouse,
    ContentSkill,
    ContentWeaponProfile,
)
from gyrinx.core.models.list import List, ListFighter
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


@pytest.mark.django_db
def test_create_list_and_add_fighter(client, user, content_house, content_fighter):
    """Test the complete flow of creating a list and adding a fighter."""
    client.force_login(user)
    
    # Create a new list
    response = client.post(
        reverse("core:lists-new"),
        {
            "name": "My Test Gang",
            "content_house": content_house.id,
        },
    )
    assert response.status_code == 302  # Redirect after creation
    
    # Get the created list
    lst = List.objects.get(name="My Test Gang")
    assert lst.owner == user
    assert lst.content_house == content_house
    
    # Navigate to the list page
    response = client.get(reverse("core:list", args=[lst.id]))
    assert response.status_code == 200
    assert "My Test Gang" in response.content.decode()
    
    # Add a fighter to the list
    response = client.post(
        reverse("core:list-fighter-new", args=[lst.id]),
        {
            "name": "Ganger Bob",
            "content_fighter": content_fighter.id,
        },
    )
    assert response.status_code == 302
    
    # Verify fighter was added
    fighter = ListFighter.objects.get(name="Ganger Bob")
    assert fighter.list == lst
    assert fighter.content_fighter == content_fighter
    
    # Check fighter appears on list page
    response = client.get(reverse("core:list", args=[lst.id]))
    assert "Ganger Bob" in response.content.decode()


@pytest.mark.django_db
def test_rename_fighter(client, user, make_list, make_list_fighter):
    """Test renaming a fighter."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Original Name")
    
    client.force_login(user)
    
    # Navigate to fighter edit page
    response = client.get(reverse("core:fighter-edit", args=[fighter.id]))
    assert response.status_code == 200
    assert "Original Name" in response.content.decode()
    
    # Rename the fighter
    response = client.post(
        reverse("core:fighter-edit", args=[fighter.id]),
        {
            "name": "New Fighter Name",
            "narrative": "A tough fighter with a new identity",
        },
    )
    assert response.status_code == 302
    
    # Verify the rename
    fighter.refresh_from_db()
    assert fighter.name == "New Fighter Name"
    assert fighter.narrative == "A tough fighter with a new identity"
    
    # Check the new name appears on list page
    response = client.get(reverse("core:list", args=[lst.id]))
    assert "New Fighter Name" in response.content.decode()
    assert "Original Name" not in response.content.decode()


@pytest.mark.django_db
def test_add_skills_to_fighter(client, user, make_list, make_list_fighter, content_fighter):
    """Test adding skills to a fighter."""
    # Create skills
    skill1 = ContentSkill.objects.create(
        name="Berserker",
        category="Ferocity",
        description="Charges with fury",
    )
    skill2 = ContentSkill.objects.create(
        name="Nerves of Steel",
        category="Cool",
        description="Steady under fire",
    )
    
    # Set fighter's primary and secondary skill categories
    content_fighter.skill_primary = "Ferocity"
    content_fighter.skill_secondary = "Cool"
    content_fighter.save()
    
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Skilled Fighter")
    
    client.force_login(user)
    
    # Navigate to fighter skills page
    response = client.get(reverse("core:fighter-skills", args=[fighter.id]))
    assert response.status_code == 200
    
    # Add skills
    response = client.post(
        reverse("core:fighter-skills", args=[fighter.id]),
        {
            "skills": [skill1.id, skill2.id],
        },
    )
    assert response.status_code == 302
    
    # Verify skills were added
    fighter.refresh_from_db()
    assert fighter.skills.count() == 2
    assert skill1 in fighter.skills.all()
    assert skill2 in fighter.skills.all()
    
    # Check skills appear on fighter page
    response = client.get(reverse("core:fighter", args=[fighter.id]))
    assert "Berserker" in response.content.decode()
    assert "Nerves of Steel" in response.content.decode()


@pytest.mark.django_db
def test_add_weapon_with_ammo(client, user, make_list, make_list_fighter):
    """Test adding a weapon with ammo from equipment list and unfiltered view."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Armed Fighter")
    
    # Create weapon and ammo
    weapon = ContentEquipment.objects.create(
        name="Bolt Pistol",
        category="Pistols",
        cost=25,
    )
    weapon_profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Bolt Pistol",
        range_short='6"',
        range_long='12"',
        strength="4",
        armour_piercing="-1",
        damage="2",
        ammo="6+",
        position=0,
    )
    
    ammo = ContentEquipment.objects.create(
        name="Bolt Rounds",
        category="Ammunition",
        cost=5,
    )
    
    client.force_login(user)
    
    # Test from equipment list view
    response = client.get(reverse("core:fighter-equipment", args=[fighter.id]))
    assert response.status_code == 200
    assert "Bolt Pistol" in response.content.decode()
    
    # Add weapon
    response = client.post(
        reverse("core:fighter-equipment-add", args=[fighter.id]),
        {
            "equipment": weapon.id,
        },
    )
    assert response.status_code == 302
    
    # Add ammo
    response = client.post(
        reverse("core:fighter-equipment-add", args=[fighter.id]),
        {
            "equipment": ammo.id,
        },
    )
    assert response.status_code == 302
    
    # Verify equipment was added
    fighter.refresh_from_db()
    assert fighter.equipment.count() == 2
    assert weapon in fighter.equipment.all()
    assert ammo in fighter.equipment.all()
    
    # Test from unfiltered view
    response = client.get(
        reverse("core:fighter-equipment", args=[fighter.id]) + "?unfiltered=1"
    )
    assert response.status_code == 200
    assert "All equipment" in response.content.decode()


@pytest.mark.django_db
def test_filter_weapons_by_category_and_availability(client, user, make_list, make_list_fighter):
    """Test filtering weapons list by category and availability."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Fighter")
    
    # Create equipment in different categories
    pistol = ContentEquipment.objects.create(
        name="Laspistol",
        category="Pistols",
        cost=10,
    )
    
    basic_weapon = ContentEquipment.objects.create(
        name="Lasgun",
        category="Basic Weapons",
        cost=15,
    )
    
    rare_weapon = ContentEquipment.objects.create(
        name="Plasma Gun",
        category="Special Weapons",
        cost=100,
        rarity="Rare (10)",
    )
    
    client.force_login(user)
    
    # Test category filter
    response = client.get(
        reverse("core:fighter-equipment", args=[fighter.id]) + "?category=Pistols"
    )
    assert response.status_code == 200
    assert "Laspistol" in response.content.decode()
    assert "Lasgun" not in response.content.decode()
    assert "Plasma Gun" not in response.content.decode()
    
    # Test availability filter (common items only)
    response = client.get(
        reverse("core:fighter-equipment", args=[fighter.id]) + "?availability=common"
    )
    assert response.status_code == 200
    assert "Laspistol" in response.content.decode()
    assert "Lasgun" in response.content.decode()
    assert "Plasma Gun" not in response.content.decode()
    
    # Test combined filters
    response = client.get(
        reverse("core:fighter-equipment", args=[fighter.id]) 
        + "?category=Special+Weapons&availability=rare"
    )
    assert response.status_code == 200
    assert "Plasma Gun" in response.content.decode()
    assert "Laspistol" not in response.content.decode()


@pytest.mark.django_db
def test_search_weapons_by_name(client, user, make_list, make_list_fighter):
    """Test searching weapons list by name."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Fighter")
    
    # Create equipment
    ContentEquipment.objects.create(name="Bolt Pistol", category="Pistols", cost=25)
    ContentEquipment.objects.create(name="Bolt Rifle", category="Basic Weapons", cost=35)
    ContentEquipment.objects.create(name="Plasma Pistol", category="Pistols", cost=50)
    
    client.force_login(user)
    
    # Search for "bolt"
    response = client.get(
        reverse("core:fighter-equipment", args=[fighter.id]) + "?search=bolt"
    )
    assert response.status_code == 200
    assert "Bolt Pistol" in response.content.decode()
    assert "Bolt Rifle" in response.content.decode()
    assert "Plasma Pistol" not in response.content.decode()
    
    # Search for "pistol"
    response = client.get(
        reverse("core:fighter-equipment", args=[fighter.id]) + "?search=pistol"
    )
    assert response.status_code == 200
    assert "Bolt Pistol" in response.content.decode()
    assert "Plasma Pistol" in response.content.decode()
    assert "Bolt Rifle" not in response.content.decode()


@pytest.mark.django_db
def test_remove_weapon(client, user, make_list, make_list_fighter, make_equipment):
    """Test removing a weapon from a fighter."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Fighter")
    weapon = make_equipment("Autogun", category="Basic Weapons", cost=15)
    
    # Add weapon to fighter
    assignment = fighter.assign(weapon)
    
    client.force_login(user)
    
    # Verify weapon is shown
    response = client.get(reverse("core:fighter", args=[fighter.id]))
    assert response.status_code == 200
    assert "Autogun" in response.content.decode()
    
    # Remove weapon
    response = client.post(
        reverse("core:fighter-equipment-remove", args=[fighter.id, assignment.id])
    )
    assert response.status_code == 302
    
    # Verify weapon was removed
    fighter.refresh_from_db()
    assert fighter.equipment.count() == 0
    
    # Check weapon no longer appears
    response = client.get(reverse("core:fighter", args=[fighter.id]))
    assert "Autogun" not in response.content.decode()


@pytest.mark.django_db
def test_add_another_fighter(client, user, make_list, make_list_fighter, make_content_fighter):
    """Test adding multiple fighters to a list."""
    lst = make_list("Test Gang")
    
    # Add first fighter
    fighter1 = make_list_fighter(lst, "Fighter One")
    
    # Create another fighter type
    content_fighter2 = make_content_fighter(
        type="Gang Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=lst.content_house,
        base_cost=110,
    )
    
    client.force_login(user)
    
    # Add second fighter
    response = client.post(
        reverse("core:list-fighter-new", args=[lst.id]),
        {
            "name": "Fighter Two",
            "content_fighter": content_fighter2.id,
        },
    )
    assert response.status_code == 302
    
    # Verify both fighters exist
    assert lst.fighters().count() == 2
    
    # Check both appear on list page
    response = client.get(reverse("core:list", args=[lst.id]))
    assert "Fighter One" in response.content.decode()
    assert "Fighter Two" in response.content.decode()
    assert "Gang Champion" in response.content.decode()


@pytest.mark.django_db
def test_rename_list_and_change_properties(client, user, make_list):
    """Test renaming a list and changing its properties."""
    lst = make_list(
        "Original Gang Name",
        narrative="Original description",
        theme_color="#FF0000",
        public=False,
    )
    
    client.force_login(user)
    
    # Navigate to list edit page
    response = client.get(reverse("core:list-edit", args=[lst.id]))
    assert response.status_code == 200
    assert "Original Gang Name" in response.content.decode()
    
    # Update list properties
    response = client.post(
        reverse("core:list-edit", args=[lst.id]),
        {
            "name": "Renamed Gang",
            "narrative": "This gang has been completely rebranded!",
            "theme_color": "#00FF00",
            "public": "on",  # Make it public
        },
    )
    assert response.status_code == 302
    
    # Verify changes
    lst.refresh_from_db()
    assert lst.name == "Renamed Gang"
    assert lst.narrative == "This gang has been completely rebranded!"
    assert lst.theme_color == "#00FF00"
    assert lst.public is True
    
    # Check changes appear on list page
    response = client.get(reverse("core:list", args=[lst.id]))
    assert "Renamed Gang" in response.content.decode()
    assert "This gang has been completely rebranded!" in response.content.decode()


@pytest.mark.django_db
def test_non_public_lists_visibility(client, user, make_user):
    """Test that non-public lists are not visible on the home page."""
    other_user = make_user("otheruser", "password")
    
    # Create content house
    house = ContentHouse.objects.create(name="Test House")
    
    # Create public and private lists
    public_list = List.objects.create(
        name="Public Gang",
        owner=user,
        content_house=house,
        public=True,
    )
    
    private_list = List.objects.create(
        name="Private Gang",
        owner=user,
        content_house=house,
        public=False,
    )
    
    other_private_list = List.objects.create(
        name="Other User Private Gang",
        owner=other_user,
        content_house=house,
        public=False,
    )
    
    # Test anonymous user on home page
    response = client.get(reverse("core:index"))
    assert response.status_code == 200
    assert "Public Gang" in response.content.decode()
    assert "Private Gang" not in response.content.decode()
    assert "Other User Private Gang" not in response.content.decode()
    
    # Test logged-in user sees their own private lists
    client.force_login(user)
    response = client.get(reverse("core:index"))
    assert response.status_code == 200
    assert "Public Gang" in response.content.decode()
    assert "Private Gang" in response.content.decode()
    assert "Other User Private Gang" not in response.content.decode()
    
    # Test on lists page
    response = client.get(reverse("core:lists"))
    assert response.status_code == 200
    assert "Public Gang" in response.content.decode()
    assert "Private Gang" not in response.content.decode()  # Lists page only shows public
    
    # Test direct access to private list by non-owner
    client.force_login(other_user)
    response = client.get(reverse("core:list", args=[private_list.id]))
    assert response.status_code == 404  # Not found for non-owner


# Additional helper fixtures for these tests
@pytest.fixture
def make_content_skill():
    """Factory for creating content skills."""
    def _make_skill(name, category, **kwargs):
        return ContentSkill.objects.create(
            name=name,
            category=category,
            **kwargs
        )
    return _make_skill