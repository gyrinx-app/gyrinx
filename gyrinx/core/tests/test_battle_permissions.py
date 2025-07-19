import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models import Battle, Campaign, List

User = get_user_model()


@pytest.mark.django_db
def test_campaign_player_can_create_battle():
    """Test that a player with a list in the campaign can create battles."""
    # Create test users
    campaign_owner = User.objects.create_user(
        username="campaignowner", password="password"
    )
    player = User.objects.create_user(username="player", password="password")

    # Create content house
    house = ContentHouse.objects.create(name="Test House")

    # Create campaign in progress
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=campaign_owner,
        status=Campaign.IN_PROGRESS,
    )

    # Create lists for player (not the campaign owner)
    player_list1 = List.objects.create(
        name="Player Gang 1",
        owner=player,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    player_list2 = List.objects.create(
        name="Player Gang 2",
        owner=player,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    campaign.lists.add(player_list1, player_list2)

    # Login as the player (not campaign owner)
    client = Client()
    client.login(username="player", password="password")

    # Test data for battle creation
    battle_data = {
        "date": "2025-01-10",
        "mission": "Territory Grab",
        "participants": [str(player_list1.id), str(player_list2.id)],
        "winners": [str(player_list1.id)],
    }

    # Create battle via view as player
    url = reverse("core:battle-new", args=[campaign.id])
    response = client.post(url, battle_data)

    # Check battle was created successfully
    assert Battle.objects.count() == 1
    battle = Battle.objects.first()
    assert battle.mission == "Territory Grab"
    assert battle.campaign == campaign
    assert battle.owner == player  # The player created it, not the campaign owner

    # Verify redirect to battle detail page
    assert response.status_code == 302
    assert response.url == reverse("core:battle", args=[battle.id])


@pytest.mark.django_db
def test_non_campaign_player_cannot_create_battle():
    """Test that a user without a list in the campaign cannot create battles."""
    # Create test users
    campaign_owner = User.objects.create_user(
        username="campaignowner", password="password"
    )
    player = User.objects.create_user(username="player", password="password")
    User.objects.create_user(username="outsider", password="password")

    # Create content house
    house = ContentHouse.objects.create(name="Test House")

    # Create campaign in progress
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=campaign_owner,
        status=Campaign.IN_PROGRESS,
    )

    # Create list for player only
    player_list = List.objects.create(
        name="Player Gang",
        owner=player,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    campaign.lists.add(player_list)

    # Login as outsider (not in campaign)
    client = Client()
    client.login(username="outsider", password="password")

    # Try to create battle
    url = reverse("core:battle-new", args=[campaign.id])
    response = client.get(url)

    # Should be redirected with error
    assert response.status_code == 302
    assert response.url == reverse("core:campaign", args=[campaign.id])

    # No battle should be created
    assert Battle.objects.count() == 0

    # Check error message was set
    messages = list(response.wsgi_request._messages)
    assert len(messages) == 1
    assert "Only players with a gang in the campaign can create battles." in str(
        messages[0]
    )


@pytest.mark.django_db
def test_campaign_owner_can_still_create_battle():
    """Test that the campaign owner can still create battles even without a list."""
    # Create test user
    campaign_owner = User.objects.create_user(
        username="campaignowner", password="password"
    )
    player = User.objects.create_user(username="player", password="password")

    # Create content house
    house = ContentHouse.objects.create(name="Test House")

    # Create campaign in progress
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=campaign_owner,
        status=Campaign.IN_PROGRESS,
    )

    # Create list for a different player
    player_list = List.objects.create(
        name="Player Gang",
        owner=player,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    campaign.lists.add(player_list)

    # Login as campaign owner
    client = Client()
    client.login(username="campaignowner", password="password")

    # Try to access battle creation page
    url = reverse("core:battle-new", args=[campaign.id])
    response = client.get(url)

    # Campaign owner without a list should be redirected
    assert response.status_code == 302
    assert response.url == reverse("core:campaign", args=[campaign.id])

    # Check error message
    messages = list(response.wsgi_request._messages)
    assert len(messages) == 1
    assert "Only players with a gang in the campaign can create battles." in str(
        messages[0]
    )
