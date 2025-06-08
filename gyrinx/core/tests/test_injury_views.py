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


def create_test_data(client):
    """Helper function to create test data."""
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

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

    # Create some injuries
    injuries = [
        ContentInjury.objects.get_or_create(
            name="Test Eye Injury View",
            defaults={
                "description": "Recovery, -1 Ballistic Skill",
                "phase": ContentInjuryDefaultOutcome.RECOVERY,
            },
        )[0],
        ContentInjury.objects.get_or_create(
            name="Test Old Battle Wound View",
            defaults={
                "description": "Roll D6 after each battle",
                "phase": ContentInjuryDefaultOutcome.ACTIVE,
            },
        )[0],
        ContentInjury.objects.get_or_create(
            name="Test Humiliated View",
            defaults={
                "description": "Convalescence, -1 Leadership, -1 Cool",
                "phase": ContentInjuryDefaultOutcome.CONVALESCENCE,
            },
        )[0],
    ]

    return user, campaign, lst, fighter, injuries


@pytest.mark.django_db
def test_add_injury_view_get():
    """Test GET request to add injury view."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    assert "Add Injury" in response.content.decode()
    assert fighter.name in response.content.decode()

    # Check that all injuries are in the form
    content = response.content.decode()
    for injury in injuries:
        assert injury.name in content


@pytest.mark.django_db
def test_add_injury_view_defaults_to_fighter_state():
    """Test that add injury view sets fighter_state to current fighter state."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    # Set fighter to RECOVERY state
    fighter.injury_state = ListFighter.RECOVERY
    fighter.save()

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200

    # Check that the form has the correct initial value
    form = response.context["form"]
    assert form.fields["fighter_state"].initial == ListFighter.RECOVERY

    # Check that RECOVERY is selected in the HTML
    content = response.content.decode()
    assert 'value="recovery" selected' in content.lower()

    # Test with CONVALESCENCE state
    fighter.injury_state = ListFighter.CONVALESCENCE
    fighter.save()

    response = client.get(url)
    form = response.context["form"]
    assert form.fields["fighter_state"].initial == ListFighter.CONVALESCENCE

    content = response.content.decode()
    assert 'value="convalescence" selected' in content.lower()


@pytest.mark.django_db
def test_add_injury_view_post_success():
    """Test successful POST to add injury."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    injury = injuries[0]  # Eye Injury

    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "recovery",
            "notes": "Shot by enemy sniper",
        },
    )

    # Should redirect to injuries edit page
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-injuries-edit", args=[lst.id, fighter.id]
    )

    # Check injury was created
    assert fighter.injuries.count() == 1
    fighter_injury = fighter.injuries.first()
    assert fighter_injury.injury == injury
    assert fighter_injury.notes == "Shot by enemy sniper"

    # Check campaign action was logged
    action = CampaignAction.objects.last()
    assert action.campaign == campaign
    assert f"{fighter.name} suffered {injury.name}" in action.description
    assert "Shot by enemy sniper" in action.description
    assert "was put into Recovery" in action.outcome


@pytest.mark.django_db
def test_add_injury_view_post_without_notes():
    """Test adding injury without notes."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    injury = injuries[1]  # Old Battle Wound

    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "active",  # Permanent injuries can keep fighter active
            "notes": "",
        },
    )

    assert response.status_code == 302

    # Check injury was created without notes
    fighter_injury = fighter.injuries.first()
    assert fighter_injury.injury == injury
    assert fighter_injury.notes == ""

    # Check campaign action doesn't include notes
    action = CampaignAction.objects.last()
    assert "suffered" in action.description
    assert " - " not in action.description  # No notes separator


@pytest.mark.django_db
def test_add_injury_non_campaign_mode():
    """Test that adding injury to non-campaign fighter is rejected."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    # Create normal list (not campaign mode)
    lst = List.objects.create(
        name="Normal List",
        content_house=house,
        owner=user,
        status=List.LIST_BUILDING,
    )

    fighter = ListFighter.objects.create(
        name="Normal Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.get(url)

    # Should redirect with error message
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[lst.id])


@pytest.mark.django_db
def test_remove_injury_view_get():
    """Test GET request to remove injury view."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    # Add an injury first
    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injuries[0],
        notes="Test injury",
        owner=user,
    )

    url = reverse(
        "core:list-fighter-injury-remove", args=[lst.id, fighter.id, fighter_injury.id]
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Remove Injury" in content
    assert fighter.name in content
    assert injuries[0].name in content
    assert injuries[0].description in content


@pytest.mark.django_db
def test_remove_injury_view_post():
    """Test POST request to remove injury."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    # Add an injury first
    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injuries[0],
        owner=user,
    )

    url = reverse(
        "core:list-fighter-injury-remove", args=[lst.id, fighter.id, fighter_injury.id]
    )
    response = client.post(url)

    # Should redirect to injuries edit page
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-injuries-edit", args=[lst.id, fighter.id]
    )

    # Check injury was removed
    assert fighter.injuries.count() == 0
    assert not ListFighterInjury.objects.filter(id=fighter_injury.id).exists()

    # Check campaign action was logged
    action = CampaignAction.objects.last()
    assert action.campaign == campaign
    assert f"{fighter.name} recovered from {injuries[0].name}" in action.description
    assert action.outcome == "Fighter became available"


@pytest.mark.django_db
def test_add_injury_wrong_user():
    """Test that users can't add injuries to other users' fighters."""
    client = Client()
    user1 = User.objects.create_user(username="user1", password="pass1")
    User.objects.create_user(username="user2", password="pass2")
    client.login(username="user2", password="pass2")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user1,
        status=Campaign.IN_PROGRESS,
    )

    # Create list owned by user1
    lst = List.objects.create(
        name="User1 List",
        content_house=house,
        owner=user1,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    fighter = ListFighter.objects.create(
        name="User1 Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user1,
    )

    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    # Try to add injury as user2
    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.post(url, {"injury": injury.id})

    # Should get 404 (list not found for this user)
    assert response.status_code == 404


@pytest.mark.django_db
def test_remove_injury_wrong_user():
    """Test that users can't remove injuries from other users' fighters."""
    client = Client()
    user1 = User.objects.create_user(username="user1", password="pass1")
    User.objects.create_user(username="user2", password="pass2")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user1,
        status=Campaign.IN_PROGRESS,
    )

    lst = List.objects.create(
        name="User1 List",
        content_house=house,
        owner=user1,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    fighter = ListFighter.objects.create(
        name="User1 Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user1,
    )

    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user1,
    )

    # Login as user2
    client.login(username="user2", password="pass2")

    # Try to remove injury as user2
    url = reverse(
        "core:list-fighter-injury-remove", args=[lst.id, fighter.id, fighter_injury.id]
    )
    response = client.post(url)

    # Should get 404
    assert response.status_code == 404

    # Injury should still exist
    assert ListFighterInjury.objects.filter(id=fighter_injury.id).exists()
