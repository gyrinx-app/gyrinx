import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentFighter
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List, ListFighter

User = get_user_model()


@pytest.mark.django_db
def test_resurrect_fighter_url_requries_login(client, user, content_house):
    """Test that the resurect fighter requires login."""
    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a content fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    # Create a dead list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
    )

    # Test unauthenticated access redirects to login
    url = reverse("core:list-fighter-resurrect", args=[lst.id, fighter.id])
    response = client.get(url)

    # Should redirect to login
    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_resurrect_fighter_url_exists_for_logged_in_user(client, user, content_house):
    """Test that the resurect fighter URL exists for logged in user."""
    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a content fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    # Create a dead list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
    )

    # Test authenticated access
    client.force_login(user)
    url = reverse("core:list-fighter-resurrect", args=[lst.id, fighter.id])
    response = client.get(url)

    # Should return 200 OK
    assert response.status_code == 200


@pytest.mark.django_db
def test_resurrect_fighter_requries_campaign_mode_list(client, user, content_house):
    """Test that resurrect fighter only works for campaign mode lists."""
    # Create a list in list building mode
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.LIST_BUILDING,
    )

    # Create a content fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    # Create a dead list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-resurrect", args=[lst.id, fighter.id])
    response = client.get(url)

    # Should redirect with error message
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[lst.id])

    # Should not change fighter state
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD


def test_resurrect_fighter_cannot_resurrect_stash(client, user, content_house):
    """Test that stash fighters cannot be resurrected."""
    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a stash fighter
    stash_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Stash",
        category="STASH",
        base_cost=0,
        is_stash=True,
    )

    # Create a list stash fighter
    fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_fighter,
        list=lst,
        owner=user,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-resurrect", args=[lst.id, fighter.id])
    response = client.get(url)

    # Should redirect with error message
    assert response.status_code == 302


@pytest.mark.django_db
def test_resurrect_fighter_marks_as_active_with_original_cost(
    client, user, content_house
):
    """Test that resurrecting a fighter marks them as active."""
    original_cost = 50

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    # Create a content fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=original_cost,
    )

    # Create a dead list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
    )

    # Resurrect the fighter
    client.force_login(user)
    url = reverse("core:list-fighter-resurrect", args=[lst.id, fighter.id])
    response = client.post(url)

    # Fighter should now be active
    assert response.status_code == 302
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.ACTIVE

    # Cost override should be cleared
    assert fighter.cost_override is None

    # Verify cost is back to original
    assert fighter.cost_int() == original_cost


@pytest.mark.django_db
def test_resurrect_fighter_confirmation_page(client, user, content_house):
    """Test that the resurrect fighter confirmation page displays correctly."""
    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a content fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    # Create a dead list fighter
    fighter = ListFighter.objects.create(
        name="Deceased Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-resurrect", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    assert b"Resurrect Fighter - Deceased Fighter" in response.content
    assert b"Are you sure you want to resurrect" in response.content
    assert b"Return them to the gang roster" in response.content
    assert b"Set their cost back to its original value" in response.content


@pytest.mark.django_db
def test_resurrect_fighter_creates_campaign_action(client, user, content_house):
    """Test that resurrecting a fighter creates a campaign action."""
    fighter_name = "Deceased Fighter"

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    # Create a content fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    # Create a dead list fighter
    fighter = ListFighter.objects.create(
        name=fighter_name,
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-resurrect", args=[lst.id, fighter.id])

    # Check no campaign actions exist yet
    assert CampaignAction.objects.count() == 0

    # Resurrect the fighter
    response = client.post(url)
    assert response.status_code == 302

    # Verify campaign action was created
    assert CampaignAction.objects.count() == 1
    action = CampaignAction.objects.first()
    assert action.campaign == campaign
    assert action.list == lst
    assert action.user == user
    assert f"Resurrection: {fighter_name} is no longer dead" in action.description
    assert f"{fighter_name} has been returned to the active roster." in action.outcome
