import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from n23.content.models import ContentHouse
from n23.core.models import Battle, Campaign, CampaignAction, List

User = get_user_model()


@pytest.mark.django_db
def test_battle_creation_creates_campaign_action():
    """Creating a battle records a campaign action framed as a new (not yet
    fought) battle, and stores participants on the through model."""
    user = User.objects.create_user(username="testuser", password="password")
    client = Client()
    client.login(username="testuser", password="password")

    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

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

    battle_data = {
        "date": "2025-01-08",
        "mission": "Gang Fight",
        "participants": [str(list1.id), str(list2.id)],
    }

    url = reverse("core:battle-new", args=[campaign.id])
    client.post(url, battle_data)

    # Battle was created, starts pre-battle, and holds both participants.
    assert Battle.objects.count() == 1
    battle = Battle.objects.first()
    assert battle.mission == "Gang Fight"
    assert battle.campaign == campaign
    assert battle.status == Battle.PRE_BATTLE
    assert battle.participants.count() == 2

    # The campaign action describes a created battle without claiming a result.
    assert CampaignAction.objects.count() == 1
    action = CampaignAction.objects.first()
    assert action.campaign == campaign
    assert action.battle == battle
    assert action.user == user
    assert "Battle created" in action.description
    assert "Gang Fight" in action.description
    assert "Gangs: Gang 1, Gang 2" in action.description
    assert action.outcome == ""


@pytest.mark.django_db
def test_battle_creation_does_not_record_winners():
    """The create form no longer accepts winners, so posting them records no
    result — a battle starts without an outcome."""
    user = User.objects.create_user(username="testuser", password="password")
    client = Client()
    client.login(username="testuser", password="password")

    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

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

    battle_data = {
        "date": "2025-01-08",
        "mission": "Sabotage",
        "participants": [str(list1.id), str(list2.id)],
        "winners": [str(list1.id)],  # ignored by the create form
    }

    url = reverse("core:battle-new", args=[campaign.id])
    client.post(url, battle_data)

    battle = Battle.objects.first()
    assert battle.winners.count() == 0

    action = CampaignAction.objects.first()
    assert action.outcome == ""
