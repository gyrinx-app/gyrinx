"""Tests for equipment advancement duplicate exclusion in the confirm flow."""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from gyrinx.content.models import (
    ContentAdvancementAssignment,
    ContentAdvancementEquipment,
    ContentEquipmentUpgrade,
)
from gyrinx.core.models import ListFighterAdvancement, ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_random_equipment_confirm_excludes_duplicate_upgrades(
    client,
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test that random equipment selection in confirm view excludes duplicate upgrades."""
    house = make_content_house("Test House")

    # Create equipment and upgrades
    weapon = make_equipment(name="Lasgun", cost=10)
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=weapon, name="Hotshot Pack", cost=20
    )
    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=weapon, name="Scope", cost=15
    )

    # Create advancement
    advancement = ContentAdvancementEquipment.objects.create(
        name="Weapon Upgrades",
        xp_cost=15,
        enable_random=True,
    )

    # Create advancement assignments with different upgrades
    assignment1 = ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=weapon,
    )
    assignment1.upgrades_field.add(upgrade1)

    assignment2 = ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=weapon,
    )
    assignment2.upgrades_field.add(upgrade2)

    # Create fighter with enough XP
    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(
        gang_list, "Test Fighter", content_fighter=fighter_type, xp_current=20
    )

    # Give fighter equipment with upgrade1
    existing_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )
    existing_assignment.upgrades_field.add(upgrade1)

    # Log in the user
    client.force_login(user)

    # Prepare the URL and data for confirm view
    url = reverse(
        "core:list-fighter-advancement-confirm", args=[gang_list.id, fighter.id]
    )
    params = {
        "advancement_choice": f"equipment_random_{advancement.id}",
        "xp_cost": 15,
        "cost_increase": 10,
    }

    # Post to confirm the advancement
    response = client.post(f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}")

    # Should redirect to list page
    assert response.status_code == 302
    expected_url = reverse("core:list", args=[gang_list.id])
    assert response.url == expected_url

    # Check that an advancement was created
    advancement_created = ListFighterAdvancement.objects.filter(fighter=fighter).first()
    assert advancement_created is not None

    # The selected assignment should NOT have upgrade1 (which fighter already has)
    assert advancement_created.equipment_assignment is not None
    selected_upgrades = list(
        advancement_created.equipment_assignment.upgrades_field.values_list(
            "id", flat=True
        )
    )
    assert upgrade1.id not in selected_upgrades
    # It should have upgrade2
    assert upgrade2.id in selected_upgrades


@pytest.mark.django_db
def test_random_equipment_confirm_shows_error_when_all_excluded(
    client,
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test error message when all random equipment options are excluded."""
    house = make_content_house("Test House")

    # Create equipment and upgrade
    weapon = make_equipment(name="Plasma Gun", cost=100)
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=weapon, name="Overcharge", cost=30
    )

    # Create advancement with only one assignment
    advancement = ContentAdvancementEquipment.objects.create(
        name="Special Weapon",
        xp_cost=30,
        enable_random=True,
    )

    assignment = ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=weapon,
    )
    assignment.upgrades_field.add(upgrade1)

    # Create fighter with enough XP
    fighter_type = make_content_fighter(
        type="Specialist",
        category=FighterCategoryChoices.CHAMPION,
        house=house,
        base_cost=80,
    )
    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(
        gang_list, "Specialist", content_fighter=fighter_type, xp_current=50
    )

    # Give fighter the same upgrade
    existing_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )
    existing_assignment.upgrades_field.add(upgrade1)

    # Log in the user
    client.force_login(user)

    # Prepare the URL and data for confirm view
    url = reverse(
        "core:list-fighter-advancement-confirm", args=[gang_list.id, fighter.id]
    )
    params = {
        "advancement_choice": f"equipment_random_{advancement.id}",
        "xp_cost": 30,
        "cost_increase": 15,
    }

    # Post to confirm the advancement
    response = client.post(f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}")

    # Should redirect to type selection page due to error
    assert response.status_code == 302
    expected_url = reverse(
        "core:list-fighter-advancement-type", args=[gang_list.id, fighter.id]
    )
    assert response.url == expected_url

    # Check for error message
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) > 0
    error_message = str(messages[0])
    assert "No available options" in error_message
    assert advancement.name in error_message

    # No advancement should have been created
    assert not ListFighterAdvancement.objects.filter(fighter=fighter).exists()


@pytest.mark.django_db
def test_random_equipment_confirm_multiple_upgrades(
    client,
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test exclusion with assignments that have multiple upgrades."""
    house = make_content_house("Test House")

    # Create equipment and upgrades
    armor = make_equipment(name="Flak Armor", cost=10)
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=armor, name="Ablative Overlay", cost=15
    )
    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=armor, name="Mesh Insert", cost=10
    )
    upgrade3 = ContentEquipmentUpgrade.objects.create(
        equipment=armor, name="Photo-goggles", cost=20
    )

    # Create advancement
    advancement = ContentAdvancementEquipment.objects.create(
        name="Armor Upgrades",
        xp_cost=25,
        enable_random=True,
    )

    # Create assignment with multiple upgrades
    assignment1 = ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=armor,
    )
    assignment1.upgrades_field.add(upgrade1, upgrade2)

    # Create assignment with different upgrade
    assignment2 = ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=armor,
    )
    assignment2.upgrades_field.add(upgrade3)

    # Create fighter with enough XP
    fighter_type = make_content_fighter(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=house,
        base_cost=100,
    )
    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(
        gang_list, "Champion", content_fighter=fighter_type, xp_current=30
    )

    # Give fighter equipment with upgrade2 (partial match with assignment1)
    existing_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=armor,
    )
    existing_assignment.upgrades_field.add(upgrade2)

    # Log in the user
    client.force_login(user)

    # Prepare the URL and data for confirm view
    url = reverse(
        "core:list-fighter-advancement-confirm", args=[gang_list.id, fighter.id]
    )
    params = {
        "advancement_choice": f"equipment_random_{advancement.id}",
        "xp_cost": 25,
        "cost_increase": 15,
    }

    # Post to confirm the advancement
    response = client.post(f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}")

    # Should redirect to list page
    assert response.status_code == 302
    expected_url = reverse("core:list", args=[gang_list.id])
    assert response.url == expected_url

    # Check that an advancement was created
    advancement_created = ListFighterAdvancement.objects.filter(fighter=fighter).first()
    assert advancement_created is not None

    # The selected assignment should be assignment2 (assignment1 excluded due to upgrade2)
    assert advancement_created.equipment_assignment == assignment2


@pytest.mark.django_db
def test_random_equipment_confirm_ignores_archived_assignments(
    client,
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test that archived fighter equipment assignments are ignored."""
    house = make_content_house("Test House")

    # Create equipment and upgrade
    weapon = make_equipment(name="Stub Gun", cost=5)
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=weapon, name="Dum-dum Rounds", cost=5
    )

    # Create advancement with one assignment
    advancement = ContentAdvancementEquipment.objects.create(
        name="Basic Equipment",
        xp_cost=5,
        enable_random=True,
    )

    assignment = ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=weapon,
    )
    assignment.upgrades_field.add(upgrade1)

    # Create fighter with enough XP
    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(
        gang_list, "Ganger", content_fighter=fighter_type, xp_current=10
    )

    # Give fighter archived equipment with the same upgrade
    archived_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
        archived=True,  # This assignment is archived
    )
    archived_assignment.upgrades_field.add(upgrade1)

    # Log in the user
    client.force_login(user)

    # Prepare the URL and data for confirm view
    url = reverse(
        "core:list-fighter-advancement-confirm", args=[gang_list.id, fighter.id]
    )
    params = {
        "advancement_choice": f"equipment_random_{advancement.id}",
        "xp_cost": 5,
        "cost_increase": 5,
    }

    # Post to confirm the advancement
    response = client.post(f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}")

    # Should redirect to list page (success)
    assert response.status_code == 302
    expected_url = reverse("core:list", args=[gang_list.id])
    assert response.url == expected_url

    # Check that an advancement was created (archived assignment should be ignored)
    advancement_created = ListFighterAdvancement.objects.filter(fighter=fighter).first()
    assert advancement_created is not None
    assert advancement_created.equipment_assignment == assignment
