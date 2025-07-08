import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models import Battle, Campaign, CampaignAction, List

User = get_user_model()


@pytest.mark.django_db
def test_battle_creation_creates_campaign_action():
    """Test that creating a battle creates a corresponding campaign action."""
    # Create test user and client
    user = User.objects.create_user(username="testuser", password="password")
    client = Client()
    client.login(username="testuser", password="password")

    # Create content house
    house = ContentHouse.objects.create(name="Test House")

    # Create campaign in progress
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    # Create test lists for participants
    list1 = List.objects.create(
        name="Gang 1",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    list2 = List.objects.create(
        name="Gang 2",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    campaign.lists.add(list1, list2)

    # Test data for battle creation
    battle_data = {
        "date": "2025-01-08",
        "mission": "Gang Fight",
        "participants": [str(list1.id), str(list2.id)],
        "winners": [str(list1.id)],
    }

    # Create battle via view
    url = reverse("core:battle-new", args=[campaign.id])
    client.post(url, battle_data)

    # Check battle was created
    assert Battle.objects.count() == 1
    battle = Battle.objects.first()
    assert battle.mission == "Gang Fight"
    assert battle.campaign == campaign

    # Check campaign action was created
    assert CampaignAction.objects.count() == 1
    action = CampaignAction.objects.first()
    assert action.campaign == campaign
    assert action.battle == battle
    assert action.user == user
    assert "Battle Report created" in action.description
    assert "Gang Fight" in action.description
    assert "Gang 1, Gang 2 participated" in action.description
    assert action.outcome == "Winners: Gang 1"


@pytest.mark.django_db
def test_battle_creation_with_draw_creates_campaign_action():
    """Test that creating a battle with no winners (draw) creates correct campaign action."""
    # Create test user and client
    user = User.objects.create_user(username="testuser", password="password")
    client = Client()
    client.login(username="testuser", password="password")

    # Create content house
    house = ContentHouse.objects.create(name="Test House")

    # Create campaign in progress
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    # Create test lists for participants
    list1 = List.objects.create(
        name="Gang A",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    list2 = List.objects.create(
        name="Gang B",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    campaign.lists.add(list1, list2)

    # Test data for battle creation with no winners (draw)
    battle_data = {
        "date": "2025-01-08",
        "mission": "Sabotage",
        "participants": [str(list1.id), str(list2.id)],
        "winners": [],  # No winners = draw
    }

    # Create battle via view
    url = reverse("core:battle-new", args=[campaign.id])
    client.post(url, battle_data)

    # Check campaign action was created with correct outcome
    action = CampaignAction.objects.first()
    assert action.outcome == "Draw"
