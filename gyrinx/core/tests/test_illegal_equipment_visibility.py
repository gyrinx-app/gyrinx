import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipmentListItem,
    ContentHouse,
    FighterCategoryChoices,
)
from gyrinx.core.models import List, ListFighter


@pytest.mark.django_db
def test_illegal_equipment_visible_with_equipment_list_filter():
    """Test that illegal equipment on fighter's equipment list is visible when equipment list filter is active."""
    # Create user
    user = User.objects.create_user(username="test_illegal_user", password="testpass")

    # Create house and fighter type
    house = ContentHouse.objects.create(name="Badzone Enforcers", generic=True)

    # Create equipment category
    gear_category = ContentEquipmentCategory.objects.create(
        name="Cyber-mastiffs",
        group="Gear",
    )

    # Create content fighter (Badzone Captain)
    content_fighter = ContentFighter.objects.create(
        house=house,
        type="Badzone Captain",
        category=FighterCategoryChoices.LEADER,
        base_cost=200,
        movement="4",
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="5+",
        cool="5+",
        willpower="6+",
        intelligence="6+",
    )

    # Create illegal equipment (Hacked cyber-mastiff)
    illegal_equipment = ContentEquipment.objects.create(
        name="Hacked cyber-mastiff",
        category=gear_category,
        rarity="I",  # Illegal
        cost="100",
    )

    # Create common equipment for comparison
    common_equipment = ContentEquipment.objects.create(
        name="Common cyber-mastiff",
        category=gear_category,
        rarity="C",  # Common
        cost="50",
    )

    # Add illegal equipment to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=illegal_equipment,
    )

    # Add common equipment to fighter's equipment list too
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=common_equipment,
    )

    # Create user list and fighter
    user_list = List.objects.create(
        name="Test Badzone Gang",
        content_house=house,
        owner=user,
    )

    list_fighter = ListFighter.objects.create(
        list=user_list,
        content_fighter=content_fighter,
        name="Test Captain",
        owner=user,
    )

    # Login
    client = Client()
    client.login(username="test_illegal_user", password="testpass")

    # Test with equipment list filter (default)
    url = reverse("core:list-fighter-gear-edit", args=[user_list.id, list_fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Both items should be visible when equipment list filter is active
    assert "Hacked cyber-mastiff" in content
    assert "Common cyber-mastiff" in content

    # Test with filter="all" and illegal NOT checked
    response = client.get(url, {"filter": "all", "al": ["C", "R"]})
    assert response.status_code == 200
    content = response.content.decode()

    # Only common item should be visible
    assert "Hacked cyber-mastiff" not in content
    assert "Common cyber-mastiff" in content

    # Test with filter="all" and illegal checked
    response = client.get(url, {"filter": "all", "al": ["C", "R", "I"]})
    assert response.status_code == 200
    content = response.content.decode()

    # Both items should be visible
    assert "Hacked cyber-mastiff" in content
    assert "Common cyber-mastiff" in content


@pytest.mark.django_db
def test_availability_filters_disabled_state():
    """Test that availability filters show disabled state when equipment list is toggled."""
    # Create user
    user = User.objects.create_user(username="test_disabled_user", password="testpass")

    # Create minimal test data
    house = ContentHouse.objects.create(name="Test House", generic=True)

    content_fighter = ContentFighter.objects.create(
        house=house,
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
        movement="4",
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="7+",
        intelligence="7+",
    )

    user_list = List.objects.create(
        name="Test Gang",
        content_house=house,
        owner=user,
    )

    list_fighter = ListFighter.objects.create(
        list=user_list,
        content_fighter=content_fighter,
        name="Test Fighter",
        owner=user,
    )

    # Login
    client = Client()
    client.login(username="test_disabled_user", password="testpass")

    # Test with equipment list filter (default)
    url = reverse("core:list-fighter-gear-edit", args=[user_list.id, list_fighter.id])
    response = client.get(url)

    assert response.status_code == 200

    # Check that is_equipment_list is True in context
    assert response.context["is_equipment_list"] is True

    content = response.content.decode()

    # Check for disabled state indicators
    assert 'class="btn btn-outline-primary btn-sm dropdown-toggle disabled"' in content
    assert (
        "Availability filters are disabled when Equipment List is toggled on" in content
    )

    # Test with filter="all"
    response = client.get(url, {"filter": "all"})
    assert response.status_code == 200

    # Check that is_equipment_list is False in context
    assert response.context["is_equipment_list"] is False

    content = response.content.decode()

    # Check that disabled state is not present
    assert (
        'class="btn btn-outline-primary btn-sm dropdown-toggle disabled"' not in content
    )
