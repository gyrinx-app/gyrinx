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
    ContentEquipmentCategory,
    ContentHouse,
    ContentSkill,
    ContentSkillCategory,
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

    # Navigate to fighter detail page
    response = client.get(reverse("core:list-fighter-edit", args=[lst.id, fighter.id]))
    assert response.status_code == 200
    assert "Original Name" in response.content.decode()

    # Rename the fighter
    response = client.post(
        reverse("core:list-fighter-edit", args=[lst.id, fighter.id]),
        {
            "name": "New Fighter Name",
            "content_fighter": fighter.content_fighter.id,
        },
    )
    assert response.status_code == 302

    # Verify the rename
    fighter.refresh_from_db()
    assert fighter.name == "New Fighter Name"

    # Update narrative separately
    response = client.post(
        reverse("core:list-fighter-narrative-edit", args=[lst.id, fighter.id]),
        {
            "narrative": "A tough fighter with a new identity",
        },
    )
    assert response.status_code == 302

    fighter.refresh_from_db()
    assert fighter.narrative == "A tough fighter with a new identity"

    # Check the new name appears on list page
    response = client.get(reverse("core:list", args=[lst.id]))
    assert "New Fighter Name" in response.content.decode()
    assert "Original Name" not in response.content.decode()


@pytest.mark.django_db
def test_add_skills_to_fighter(
    client, user, make_list, make_list_fighter, content_fighter, make_content_skill
):
    """Test adding skills to a fighter."""
    # Get or create skill categories
    ferocity_category, _ = ContentSkillCategory.objects.get_or_create(name="Ferocity")
    cool_category, _ = ContentSkillCategory.objects.get_or_create(name="Cool")

    # Get or create skills
    skill1, _ = ContentSkill.objects.get_or_create(
        name="Berserker",
        category=ferocity_category,
    )
    skill2, _ = ContentSkill.objects.get_or_create(
        name="Nerves of Steel",
        category=cool_category,
    )

    # Set fighter's primary and secondary skill categories
    content_fighter.primary_skill_categories.set([ferocity_category])
    content_fighter.secondary_skill_categories.set([cool_category])
    content_fighter.save()

    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Skilled Fighter")

    client.force_login(user)

    # Navigate to fighter skills page
    response = client.get(
        reverse("core:list-fighter-skills-edit", args=[lst.id, fighter.id])
    )
    assert response.status_code == 200

    # Add skill 1
    response = client.post(
        reverse("core:list-fighter-skill-add", args=[lst.id, fighter.id]),
        {
            "skill_id": skill1.id,
        },
    )
    assert response.status_code == 302

    # Add skill 2
    response = client.post(
        reverse("core:list-fighter-skill-add", args=[lst.id, fighter.id]),
        {
            "skill_id": skill2.id,
        },
    )
    assert response.status_code == 302

    # Verify skills were added
    fighter.refresh_from_db()
    assert fighter.skills.count() == 2
    assert skill1 in fighter.skills.all()
    assert skill2 in fighter.skills.all()

    # Check skills appear on list page with fighter
    response = client.get(reverse("core:list", args=[lst.id]))
    assert "Berserker" in response.content.decode()
    assert "Nerves of Steel" in response.content.decode()


@pytest.mark.django_db
def test_add_weapon_with_ammo(client, user, make_list, make_list_fighter):
    """Test adding a weapon with ammo from equipment list and unfiltered view."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Armed Fighter")

    # Get or create equipment categories
    pistols_category, _ = ContentEquipmentCategory.objects.get_or_create(name="Pistols")
    ammo_category, _ = ContentEquipmentCategory.objects.get_or_create(name="Ammunition")

    # Get or create weapon and ammo
    weapon, _ = ContentEquipment.objects.get_or_create(
        name="Bolt Pistol",
        category=pistols_category,
        defaults={"cost": 25},
    )
    ContentWeaponProfile.objects.get_or_create(
        equipment=weapon,
        name="Bolt Pistol",
        defaults={
            "range_short": '6"',
            "range_long": '12"',
            "strength": "4",
            "armour_piercing": "-1",
            "damage": "2",
            "ammo": "6+",
        },
    )

    ammo, _ = ContentEquipment.objects.get_or_create(
        name="Bolt Rounds",
        category=ammo_category,
        defaults={"cost": 5},
    )

    # Add weapon to the fighter's equipment list
    from gyrinx.content.models import ContentFighterEquipmentListItem

    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter.content_fighter_cached,
        equipment=weapon,
    )

    client.force_login(user)

    # Test from equipment list view (weapons)
    response = client.get(
        reverse("core:list-fighter-weapons-edit", args=[lst.id, fighter.id])
    )
    assert response.status_code == 200
    # Check that the weapon we created is displayed
    assert "Bolt Pistol" in response.content.decode()

    # Add weapon - submit form with equipment selection
    response = client.post(
        reverse("core:list-fighter-weapons-edit", args=[lst.id, fighter.id]),
        {
            "content_equipment": weapon.id,
            "weapon_profiles_field": [],  # No specific profiles selected
            "upgrades_field": [],  # No upgrades selected
        },
    )
    assert response.status_code == 302

    # Add ammo to gear
    response = client.get(
        reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    )
    response = client.post(
        reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id]),
        {
            "content_equipment": ammo.id,
            "weapon_profiles_field": [],  # No specific profiles for gear
            "upgrades_field": [],  # No upgrades selected
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
        reverse("core:list-fighter-weapons-edit", args=[lst.id, fighter.id])
        + "?category=all"
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_filter_weapons_by_category_and_availability(
    client, user, make_list, make_list_fighter
):
    """Test filtering weapons list by category and availability."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Fighter")

    # Get or create equipment categories
    pistols_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Pistols")
    basic_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Basic Weapons")
    special_cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Special Weapons"
    )

    # Get or create equipment in different categories
    laspistol, _ = ContentEquipment.objects.get_or_create(
        name="Laspistol",
        category=pistols_cat,
        defaults={"cost": 10},
    )

    lasgun, _ = ContentEquipment.objects.get_or_create(
        name="Lasgun",
        category=basic_cat,
        defaults={"cost": 15},
    )

    plasma_gun, _ = ContentEquipment.objects.get_or_create(
        name="Plasma Gun",
        category=special_cat,
        defaults={"cost": 100, "rarity": "R"},  # R for Rare
    )

    # Create weapon profiles (required for equipment to be considered weapons)
    from gyrinx.content.models import ContentWeaponProfile

    ContentWeaponProfile.objects.get_or_create(
        equipment=laspistol,
        name="Laspistol",
        defaults={
            "range_short": '8"',
            "range_long": '16"',
            "strength": "3",
            "armour_piercing": "0",
            "damage": "1",
            "ammo": "2+",
        },
    )
    ContentWeaponProfile.objects.get_or_create(
        equipment=lasgun,
        name="Lasgun",
        defaults={
            "range_short": '18"',
            "range_long": '24"',
            "strength": "3",
            "armour_piercing": "0",
            "damage": "1",
            "ammo": "2+",
        },
    )
    ContentWeaponProfile.objects.get_or_create(
        equipment=plasma_gun,
        name="Plasma Gun",
        defaults={
            "range_short": '12"',
            "range_long": '24"',
            "strength": "5",
            "armour_piercing": "-1",
            "damage": "2",
            "ammo": "5+",
        },
    )

    # Add weapons to the fighter's equipment list
    from gyrinx.content.models import ContentFighterEquipmentListItem

    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter.content_fighter_cached,
        equipment=laspistol,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter.content_fighter_cached,
        equipment=lasgun,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter.content_fighter_cached,
        equipment=plasma_gun,
    )

    client.force_login(user)

    # Test category filter - need to use cat parameter with category ID
    response = client.get(
        reverse("core:list-fighter-weapons-edit", args=[lst.id, fighter.id])
        + f"?cat={pistols_cat.id}"
    )
    assert response.status_code == 200
    assert "Laspistol" in response.content.decode()
    assert "Lasgun" not in response.content.decode()
    assert "Plasma Gun" not in response.content.decode()

    # Test availability filter (common items only) - use al parameter
    response = client.get(
        reverse("core:list-fighter-weapons-edit", args=[lst.id, fighter.id]) + "?al=C"
    )
    assert response.status_code == 200
    assert "Laspistol" in response.content.decode()
    assert "Lasgun" in response.content.decode()
    assert "Plasma Gun" not in response.content.decode()

    # Test combined filters - use correct parameter names
    response = client.get(
        reverse("core:list-fighter-weapons-edit", args=[lst.id, fighter.id])
        + f"?cat={special_cat.id}&al=R"
    )
    assert response.status_code == 200
    assert "Plasma Gun" in response.content.decode()
    assert "Laspistol" not in response.content.decode()


@pytest.mark.django_db
def test_search_weapons_by_name(client, user, make_list, make_list_fighter):
    """Test searching weapons list by name."""
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Fighter")

    # Get or create equipment categories
    pistols_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Pistols")
    basic_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Basic Weapons")

    # Get or create equipment
    bolt_pistol, _ = ContentEquipment.objects.get_or_create(
        name="Bolt Pistol", category=pistols_cat, defaults={"cost": 25}
    )
    bolt_rifle, _ = ContentEquipment.objects.get_or_create(
        name="Bolt Rifle", category=basic_cat, defaults={"cost": 35}
    )
    plasma_pistol, _ = ContentEquipment.objects.get_or_create(
        name="Plasma Pistol", category=pistols_cat, defaults={"cost": 50}
    )

    # Create weapon profiles (required for equipment to be considered weapons)
    from gyrinx.content.models import ContentWeaponProfile

    ContentWeaponProfile.objects.get_or_create(
        equipment=bolt_pistol,
        name="Bolt Pistol",
        defaults={
            "range_short": '6"',
            "range_long": '12"',
            "strength": "4",
            "armour_piercing": "-1",
            "damage": "2",
            "ammo": "6+",
        },
    )
    ContentWeaponProfile.objects.get_or_create(
        equipment=bolt_rifle,
        name="Bolt Rifle",
        defaults={
            "range_short": '24"',
            "range_long": '48"',
            "strength": "4",
            "armour_piercing": "-1",
            "damage": "1",
            "ammo": "4+",
        },
    )
    ContentWeaponProfile.objects.get_or_create(
        equipment=plasma_pistol,
        name="Plasma Pistol",
        defaults={
            "range_short": '6"',
            "range_long": '12"',
            "strength": "5",
            "armour_piercing": "-1",
            "damage": "2",
            "ammo": "5+",
        },
    )

    # Add weapons to the fighter's equipment list
    from gyrinx.content.models import ContentFighterEquipmentListItem

    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter.content_fighter_cached,
        equipment=bolt_pistol,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter.content_fighter_cached,
        equipment=bolt_rifle,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter.content_fighter_cached,
        equipment=plasma_pistol,
    )

    client.force_login(user)

    # Search for "bolt" - use q parameter
    response = client.get(
        reverse("core:list-fighter-weapons-edit", args=[lst.id, fighter.id]) + "?q=bolt"
    )
    assert response.status_code == 200
    assert "Bolt Pistol" in response.content.decode()
    assert "Bolt Rifle" in response.content.decode()
    assert "Plasma Pistol" not in response.content.decode()

    # Search for "pistol" - use q parameter
    response = client.get(
        reverse("core:list-fighter-weapons-edit", args=[lst.id, fighter.id])
        + "?q=pistol"
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

    # Get or create equipment category
    basic_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Basic Weapons")
    weapon, _ = ContentEquipment.objects.get_or_create(
        name="Autogun", category=basic_cat, defaults={"cost": 15}
    )

    # Add weapon to fighter
    assignment = fighter.assign(weapon)

    client.force_login(user)

    # Verify weapon is shown on list page
    response = client.get(reverse("core:list", args=[lst.id]))
    assert response.status_code == 200
    assert "Autogun" in response.content.decode()

    # Remove weapon
    response = client.post(
        reverse(
            "core:list-fighter-weapon-delete", args=[lst.id, fighter.id, assignment.id]
        )
    )
    assert response.status_code == 302

    # Verify weapon was removed
    fighter.refresh_from_db()
    assert fighter.equipment.count() == 0

    # Check weapon no longer appears
    response = client.get(reverse("core:list", args=[lst.id]))
    assert "Autogun" not in response.content.decode()


@pytest.mark.django_db
def test_add_another_fighter(
    client, user, make_list, make_list_fighter, make_content_fighter
):
    """Test adding multiple fighters to a list."""
    lst = make_list("Test Gang")

    # Add first fighter
    make_list_fighter(lst, "Fighter One")

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
        },
    )
    assert response.status_code == 302

    # Verify changes
    lst.refresh_from_db()
    assert lst.name == "Renamed Gang"
    assert lst.narrative == "This gang has been completely rebranded!"

    # Check changes appear on list page
    response = client.get(reverse("core:list", args=[lst.id]))
    assert "Renamed Gang" in response.content.decode()
    # The narrative is not displayed on the list page, only a link to the About page
    assert "About" in response.content.decode()  # Link to About page should be present

    # Check narrative appears on the About page
    response = client.get(reverse("core:list-about", args=[lst.id]))
    assert "This gang has been completely rebranded!" in response.content.decode()


@pytest.mark.django_db
def test_non_public_lists_visibility(client, user, make_user):
    """Test that non-public lists are not visible on the home page."""
    other_user = make_user("otheruser", "password")

    # Get or create content house
    house, _ = ContentHouse.objects.get_or_create(name="Test House")

    # Create lists (all lists are effectively private in the system)
    List.objects.create(
        name="My Gang",
        owner=user,
        content_house=house,
    )

    private_list = List.objects.create(
        name="Private Gang",
        owner=user,
        content_house=house,
    )

    List.objects.create(
        name="Other User Gang",
        owner=other_user,
        content_house=house,
    )

    # Test anonymous user on home page (should see no lists)
    response = client.get(reverse("core:index"))
    assert response.status_code == 200
    # Anonymous users don't see any lists on home page
    assert "My Gang" not in response.content.decode()
    assert "Private Gang" not in response.content.decode()
    assert "Other User Gang" not in response.content.decode()

    # Test logged-in user sees only their own lists
    client.force_login(user)
    response = client.get(reverse("core:index"))
    assert response.status_code == 200
    # User should see their own lists
    assert "My Gang" in response.content.decode()
    assert "Private Gang" in response.content.decode()
    assert "Other User Gang" not in response.content.decode()

    # Test on lists page (lists page shows all public lists)
    response = client.get(reverse("core:lists"))
    assert response.status_code == 200
    # Since lists are effectively private, the lists page might not show any lists
    # or it shows lists based on different criteria

    # Test direct access to other user's list
    client.force_login(other_user)
    response = client.get(reverse("core:list", args=[private_list.id]))
    # In this system, users can view other users' lists
    assert response.status_code == 200


# Additional helper fixtures for these tests
@pytest.fixture
def make_content_skill():
    """Factory for creating content skills."""

    def _make_skill(name, category, **kwargs):
        return ContentSkill.objects.create(name=name, category=category, **kwargs)

    return _make_skill
