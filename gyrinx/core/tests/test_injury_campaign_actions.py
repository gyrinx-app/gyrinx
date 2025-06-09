import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentInjury,
    ContentInjuryDefaultOutcome,
)
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List, ListFighter, ListFighterInjury
from gyrinx.models import FighterCategoryChoices


def create_test_campaign_data():
    """Helper function to create test data with campaign."""
    user = User.objects.create_user(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    return user, campaign, lst, fighter


@pytest.mark.django_db
def test_injury_campaign_action_creation():
    """Test that adding an injury creates a campaign action."""
    user, campaign, lst, fighter = create_test_campaign_data()

    injury = ContentInjury.objects.create(
        name="Spinal Injury",
        description="Recovery, -1 Strength",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    # No campaign actions initially
    assert CampaignAction.objects.count() == 0

    # Add injury via the view
    client = Client()
    client.login(username="testuser", password="testpass")

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "recovery",
            "notes": "Fell from platform",
        },
    )

    assert response.status_code == 302

    # Check campaign action was created
    assert CampaignAction.objects.count() == 1
    action = CampaignAction.objects.first()

    assert action.campaign == campaign
    assert action.owner == user
    assert f"{fighter.name} suffered {injury.name}" in action.description
    assert "Fell from platform" in action.description
    assert action.outcome == f"{fighter.name} was put into Recovery"


@pytest.mark.django_db
def test_injury_campaign_action_without_notes():
    """Test campaign action when injury has no notes."""
    user, campaign, lst, fighter = create_test_campaign_data()

    injury = ContentInjury.objects.create(
        name="Out Cold",
        description="",  # No description
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    client = Client()
    client.login(username="testuser", password="testpass")

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "recovery",  # Out Cold defaults to recovery
            "notes": "",  # No notes
        },
    )

    assert response.status_code == 302

    # Check campaign action
    action = CampaignAction.objects.first()
    assert action.description == f"Injury: {fighter.name} suffered {injury.name}"
    assert action.outcome == f"{fighter.name} was put into Recovery"


@pytest.mark.django_db
def test_injury_removal_campaign_action():
    """Test that removing an injury creates a campaign action."""
    user, campaign, lst, fighter = create_test_campaign_data()

    injury = ContentInjury.objects.create(
        name="Eye Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    # Add injury first
    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user,
    )

    # Clear any existing actions
    CampaignAction.objects.all().delete()

    # Remove injury via the view
    client = Client()
    client.login(username="testuser", password="testpass")

    url = reverse(
        "core:list-fighter-injury-remove", args=[lst.id, fighter.id, fighter_injury.id]
    )
    response = client.post(url)

    assert response.status_code == 302

    # Check campaign action was created
    assert CampaignAction.objects.count() == 1
    action = CampaignAction.objects.first()

    assert action.campaign == campaign
    assert action.owner == user
    assert (
        action.description == f"Recovery: {fighter.name} recovered from {injury.name}"
    )
    assert action.outcome == "Fighter became available"


@pytest.mark.django_db
def test_no_campaign_action_without_campaign():
    """Test that no campaign action is created when list has no campaign."""
    user = User.objects.create_user(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    # Create list in campaign mode but without a campaign
    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=None,  # No campaign
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    # Add injury via the view
    client = Client()
    client.login(username="testuser", password="testpass")

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "recovery",
            "notes": "Test notes",
        },
    )

    assert response.status_code == 302

    # No campaign action should be created
    assert CampaignAction.objects.count() == 0

    # But injury should still be added
    assert fighter.injuries.count() == 1


@pytest.mark.django_db
def test_campaign_action_with_injury_description():
    """Test campaign action includes injury description in outcome."""
    user, campaign, lst, fighter = create_test_campaign_data()

    injury = ContentInjury.objects.create(
        name="Humiliated",
        description="Convalescence, -1 Leadership, -1 Cool",
        phase=ContentInjuryDefaultOutcome.CONVALESCENCE,
    )

    client = Client()
    client.login(username="testuser", password="testpass")

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "convalescence",
            "notes": "Lost in a duel",
        },
    )

    assert response.status_code == 302

    # Check campaign action outcome includes fighter state
    action = CampaignAction.objects.first()
    assert action.outcome == f"{fighter.name} was put into Convalescence"


@pytest.mark.django_db
def test_campaign_action_user_tracking():
    """Test that campaign actions track the correct user."""
    user1, campaign, lst, fighter = create_test_campaign_data()
    user2 = User.objects.create_user(username="user2", password="pass2")

    # Make user2 also an owner (for testing)
    lst.owner = user2
    lst.save()
    fighter.owner = user2
    fighter.save()
    campaign.owner = user2
    campaign.save()

    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    # Add injury as user2
    client = Client()
    client.login(username="user2", password="pass2")

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "recovery",
            "notes": "Test",
        },
    )

    assert response.status_code == 302

    # Check campaign action is owned by user2
    action = CampaignAction.objects.first()
    assert action.owner == user2

    # Check history tracking
    assert action.history.count() == 1
    assert action.history.first().history_user == user2


@pytest.mark.django_db
def test_multiple_injuries_multiple_actions():
    """Test that each injury creates its own campaign action."""
    user, campaign, lst, fighter = create_test_campaign_data()

    injuries = [
        ContentInjury.objects.create(
            name="Injury 1",
            phase=ContentInjuryDefaultOutcome.RECOVERY,
        ),
        ContentInjury.objects.create(
            name="Injury 2",
            phase=ContentInjuryDefaultOutcome.DEAD,
        ),
        ContentInjury.objects.create(
            name="Injury 3",
            phase=ContentInjuryDefaultOutcome.CONVALESCENCE,
        ),
    ]

    client = Client()
    client.login(username="testuser", password="testpass")

    # Add each injury
    for i, injury in enumerate(injuries):
        url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
        response = client.post(
            url,
            {
                "injury": injury.id,
                "fighter_state": ["recovery", "active", "convalescence"][i],
                "notes": f"Notes for injury {i + 1}",
            },
        )
        assert response.status_code == 302

    # Should have 3 campaign actions
    assert CampaignAction.objects.count() == 3

    # Check each action
    actions = CampaignAction.objects.order_by("created")
    for i, action in enumerate(actions):
        assert f"suffered {injuries[i].name}" in action.description
        assert f"Notes for injury {i + 1}" in action.description


@pytest.mark.django_db
def test_injury_and_removal_campaign_actions():
    """Test full cycle of adding and removing injury with campaign actions."""
    user, campaign, lst, fighter = create_test_campaign_data()

    injury = ContentInjury.objects.create(
        name="Broken Ribs",
        description="Recovery phase injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    client = Client()
    client.login(username="testuser", password="testpass")

    # Add injury
    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "recovery",
            "notes": "Hit by hammer",
        },
    )
    assert response.status_code == 302

    # Get the created injury
    fighter_injury = fighter.injuries.first()

    # Remove injury
    url = reverse(
        "core:list-fighter-injury-remove", args=[lst.id, fighter.id, fighter_injury.id]
    )
    response = client.post(url)
    assert response.status_code == 302

    # Should have 2 campaign actions
    assert CampaignAction.objects.count() == 2

    actions = list(CampaignAction.objects.order_by("created"))

    # First action: injury added
    assert "suffered Broken Ribs" in actions[0].description
    assert "Hit by hammer" in actions[0].description

    # Second action: injury removed
    assert "recovered from Broken Ribs" in actions[1].description
    assert actions[1].outcome == "Fighter became available"
