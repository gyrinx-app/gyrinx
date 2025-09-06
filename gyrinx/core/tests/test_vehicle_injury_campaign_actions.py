"""
Test campaign action text for vehicle injuries/damage.
"""

import pytest
from django.contrib.auth import get_user_model

from gyrinx.content.models import (
    ContentFighter,
    ContentFighterCategoryTerms,
    ContentHouse,
    ContentInjury,
    FighterCategoryChoices,
)
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List, ListFighter, ListFighterInjury

User = get_user_model()


@pytest.fixture
def test_data(db):
    """Create test data for vehicle injury tests."""
    user = User.objects.create_user(username="test_user", password="test_password")
    house = ContentHouse.objects.create(name="Test House")

    # Create terminology for vehicles
    ContentFighterCategoryTerms.objects.create(
        categories=[FighterCategoryChoices.VEHICLE],
        singular="Vehicle",
        proximal_demonstrative="The vehicle",
        injury_singular="Damage",
        injury_plural="Damage",
        recovery_singular="Repair",
    )

    # Create a vehicle fighter
    vehicle = ContentFighter.objects.create(
        type="Test Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=100,
    )

    # Create a regular fighter for comparison
    regular_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )

    injury = ContentInjury.objects.create(
        name="Write-off",
        description="Vehicle is destroyed",
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
    )

    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
        campaign=campaign,
        status=List.CAMPAIGN_MODE,
    )

    vehicle_fighter = ListFighter.objects.create(
        name="Svenotar Scout Trike",
        content_fighter=vehicle,
        list=lst,
        owner=user,
    )

    regular_list_fighter = ListFighter.objects.create(
        name="Regular Ganger",
        content_fighter=regular_fighter,
        list=lst,
        owner=user,
    )

    return {
        "user": user,
        "house": house,
        "vehicle": vehicle,
        "regular_fighter": regular_fighter,
        "injury": injury,
        "campaign": campaign,
        "list": lst,
        "vehicle_fighter": vehicle_fighter,
        "regular_list_fighter": regular_list_fighter,
    }


@pytest.mark.django_db
def test_vehicle_injury_uses_damage_terminology(test_data, client):
    """Test that vehicles use 'Damage:' instead of 'Injury:' in campaign actions."""
    client.login(username="test_user", password="test_password")

    # Add an injury to the vehicle
    response = client.post(
        f"/list/{test_data['list'].id}/fighter/{test_data['vehicle_fighter'].id}/injury/add",
        {
            "injury": test_data["injury"].id,
            "fighter_state": ListFighter.ACTIVE,
            "notes": "Hit by enemy fire",
        },
    )

    # Check that the request succeeded
    assert response.status_code in [200, 302], (
        f"Response status: {response.status_code}, content: {response.content[:500] if hasattr(response, 'content') else 'No content'}"
    )

    # Check the campaign action was created with correct terminology
    action = CampaignAction.objects.filter(
        campaign=test_data["campaign"],
        list=test_data["list"],
    ).first()

    assert action is not None
    assert (
        action.description
        == f"Damage: {test_data['vehicle_fighter'].name} suffered {test_data['injury'].name} - Hit by enemy fire"
    )


@pytest.mark.django_db
def test_regular_fighter_injury_uses_injury_terminology(test_data, client):
    """Test that regular fighters use 'Injury:' in campaign actions."""
    client.login(username="test_user", password="test_password")

    # Add an injury to the regular fighter
    client.post(
        f"/list/{test_data['list'].id}/fighter/{test_data['regular_list_fighter'].id}/injury/add",
        {
            "injury": test_data["injury"].id,
            "fighter_state": ListFighter.ACTIVE,
            "notes": "Shot in combat",
        },
    )

    # Check the campaign action was created with correct terminology
    action = CampaignAction.objects.filter(
        campaign=test_data["campaign"],
        list=test_data["list"],
        description__contains=test_data["regular_list_fighter"].name,
    ).first()

    assert action is not None
    assert (
        action.description
        == f"Injury: {test_data['regular_list_fighter'].name} suffered {test_data['injury'].name} - Shot in combat"
    )


@pytest.mark.django_db
def test_vehicle_recovery_uses_repair_terminology(test_data, client):
    """Test that vehicles use 'Repair:' instead of 'Recovery:' when removing injuries."""
    client.login(username="test_user", password="test_password")

    # First add an injury to the vehicle
    injury_obj = ListFighterInjury.objects.create_with_user(
        user=test_data["user"],
        fighter=test_data["vehicle_fighter"],
        injury=test_data["injury"],
        owner=test_data["user"],
    )

    # Remove the injury
    client.post(
        f"/list/{test_data['list'].id}/fighter/{test_data['vehicle_fighter'].id}/injury/{injury_obj.id}/remove",
    )

    # Check the campaign action was created with correct terminology
    action = CampaignAction.objects.filter(
        campaign=test_data["campaign"],
        list=test_data["list"],
        description__contains="Repair:",
    ).first()

    assert action is not None
    assert (
        action.description
        == f"Repair: {test_data['vehicle_fighter'].name} recovered from {test_data['injury'].name}"
    )


@pytest.mark.django_db
def test_regular_fighter_recovery_uses_recovery_terminology(test_data, client):
    """Test that regular fighters use 'Recovery:' when removing injuries."""
    client.login(username="test_user", password="test_password")

    # First add an injury to the regular fighter
    injury_obj = ListFighterInjury.objects.create_with_user(
        user=test_data["user"],
        fighter=test_data["regular_list_fighter"],
        injury=test_data["injury"],
        owner=test_data["user"],
    )

    # Remove the injury
    client.post(
        f"/list/{test_data['list'].id}/fighter/{test_data['regular_list_fighter'].id}/injury/{injury_obj.id}/remove",
    )

    # Check the campaign action was created with correct terminology
    action = CampaignAction.objects.filter(
        campaign=test_data["campaign"],
        list=test_data["list"],
        description__contains="Recovery:",
    ).first()

    assert action is not None
    assert (
        action.description
        == f"Recovery: {test_data['regular_list_fighter'].name} recovered from {test_data['injury'].name}"
    )
