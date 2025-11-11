import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentFighter
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List, ListFighter

User = get_user_model()


@pytest.mark.django_db
def test_fighter_state_edit_requires_campaign_mode(client, user, content_house):
    """Test that fighter state edit only works in campaign mode."""
    # Create a list building mode list
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

    # Create a list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-state-edit", args=[lst.id, fighter.id])
    response = client.get(url)

    # Should redirect with error message
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[lst.id])


@pytest.mark.django_db
def test_fighter_state_edit_changes_state(client, user, content_house):
    """Test that fighter state can be changed."""
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

    # Create a list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.ACTIVE,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-state-edit", args=[lst.id, fighter.id])

    # Change to recovery state
    response = client.post(
        url,
        {
            "fighter_state": ListFighter.RECOVERY,
            "reason": "Test reason",
        },
    )

    # Should redirect to injuries edit page
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-injuries-edit", args=[lst.id, fighter.id]
    )

    # Check state was changed
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.RECOVERY

    # Check campaign action was created
    action = CampaignAction.objects.last()
    assert action.campaign == campaign
    assert "State Change" in action.description
    assert "Test reason" in action.description


@pytest.mark.django_db
def test_fighter_state_edit_dead_redirects_to_kill(client, user, content_house):
    """Test that changing state to dead redirects to kill confirmation."""
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

    # Create a list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.RECOVERY,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-state-edit", args=[lst.id, fighter.id])

    # Try to change to dead state
    response = client.post(
        url,
        {
            "fighter_state": ListFighter.DEAD,
            "reason": "Fatal injuries",
        },
    )

    # Should redirect to kill confirmation page
    assert response.status_code == 302
    assert response.url == reverse("core:list-fighter-kill", args=[lst.id, fighter.id])

    # Check state was NOT changed yet (kill view should handle it)
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.RECOVERY  # Still recovery

    # Check no campaign action was created yet
    assert CampaignAction.objects.count() == 0


@pytest.mark.django_db
def test_fighter_state_edit_active_redirects_to_resurrect(client, user, content_house):
    """Test that changing state to active redirects to resurrect confirmation."""
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

    # Create a list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-state-edit", args=[lst.id, fighter.id])

    # Try to change to active state
    response = client.post(
        url,
        {
            "fighter_state": ListFighter.ACTIVE,
            "reason": "Resurrected",
        },
    )

    # Should redirect to resurrect confirmation page
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-resurrect", args=[lst.id, fighter.id]
    )

    # Check state was NOT changed yet (resurrect view should handle it)
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD  # Still dead

    # Check no campaign action was created yet
    assert CampaignAction.objects.count() == 0


@pytest.mark.django_db
def test_fighter_state_edit_no_change(client, user, content_house):
    """Test that no change when state is the same."""
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

    # Create a list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.RECOVERY,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-state-edit", args=[lst.id, fighter.id])

    # Try to change to same state
    response = client.post(
        url,
        {
            "fighter_state": ListFighter.RECOVERY,
            "reason": "No change",
        },
    )

    # Should redirect to injuries edit page
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-injuries-edit", args=[lst.id, fighter.id]
    )

    # Check state was not changed
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.RECOVERY

    # Check no campaign action was created
    assert CampaignAction.objects.count() == 0
