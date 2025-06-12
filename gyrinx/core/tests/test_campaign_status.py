import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List

User = get_user_model()


@pytest.mark.django_db
def test_campaign_default_status(client):
    """Test that new campaigns default to pre-campaign status."""
    User.objects.create_user(username="testuser", password="password")
    client.login(username="testuser", password="password")

    client.post(
        reverse("core:campaigns-new"),
        data={
            "name": "Test Campaign",
            "summary": "Test summary",
            "narrative": "Test narrative",
            "public": True,
        },
    )

    campaign = Campaign.objects.get(name="Test Campaign")
    assert campaign.status == Campaign.PRE_CAMPAIGN
    assert campaign.is_pre_campaign
    assert not campaign.is_in_progress
    assert not campaign.is_post_campaign


@pytest.mark.django_db
def test_campaign_status_transitions(client):
    """Test campaign status transitions and permissions."""
    user = User.objects.create_user(username="testuser", password="password")

    # Create a house
    house = ContentHouse.objects.create(
        name="Test House",
    )

    # Create a campaign
    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Test Campaign",
        owner=user,
    )

    # Create a list to add to the campaign
    list_obj = List.objects.create_with_user(
        user=user,
        name="Test List",
        owner=user,
        content_house=house,
    )

    # Cannot start campaign without lists
    assert not campaign.can_start_campaign()
    assert not campaign.start_campaign()

    # Add list to campaign
    campaign.lists.add(list_obj)

    # Now can start campaign
    assert campaign.can_start_campaign()
    assert not campaign.can_end_campaign()

    # Test starting campaign via view as owner
    client.login(username="testuser", password="password")

    # First, GET should show confirmation page
    response = client.get(reverse("core:campaign-start", args=[campaign.id]))
    assert response.status_code == 200
    assert b"Are you sure you want to start this campaign?" in response.content

    # Then POST to actually start it
    response = client.post(reverse("core:campaign-start", args=[campaign.id]))
    assert response.status_code == 302

    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS
    assert campaign.is_in_progress
    assert not campaign.can_start_campaign()
    assert campaign.can_end_campaign()

    # Test ending campaign
    # First, GET should show confirmation page
    response = client.get(reverse("core:campaign-end", args=[campaign.id]))
    assert response.status_code == 200
    assert b"Are you sure you want to end this campaign?" in response.content
    assert b"you will be able to reopen it later if needed" in response.content

    # Then POST to actually end it
    response = client.post(reverse("core:campaign-end", args=[campaign.id]))
    assert response.status_code == 302

    campaign.refresh_from_db()
    assert campaign.status == Campaign.POST_CAMPAIGN
    assert campaign.is_post_campaign
    assert not campaign.can_start_campaign()
    assert not campaign.can_end_campaign()


@pytest.mark.django_db
def test_campaign_reopen_functionality(client):
    """Test that ended campaigns can be reopened."""
    owner = User.objects.create_user(username="owner", password="password")
    client.login(username="owner", password="password")

    # Create a house
    house = ContentHouse.objects.create(
        name="Test House",
    )

    # Create a campaign
    campaign = Campaign.objects.create_with_user(
        user=owner,
        name="Test Campaign",
        owner=owner,
    )

    # Add a list so we can start the campaign
    list_obj = List.objects.create_with_user(
        user=owner,
        name="Test List",
        owner=owner,
        content_house=house,
    )
    campaign.lists.add(list_obj)

    # Start the campaign
    campaign.start_campaign()
    assert campaign.status == Campaign.IN_PROGRESS

    # End the campaign
    campaign.end_campaign()
    assert campaign.status == Campaign.POST_CAMPAIGN
    assert campaign.can_reopen_campaign()

    # Get the number of lists before reopening
    lists_before = campaign.lists.count()

    # Test reopening via view
    # First, GET should show confirmation page
    response = client.get(reverse("core:campaign-reopen", args=[campaign.id]))
    assert response.status_code == 200
    assert b"Are you sure you want to reopen this campaign?" in response.content
    assert b"No new clones will be created" in response.content

    # Then POST to actually reopen it
    response = client.post(reverse("core:campaign-reopen", args=[campaign.id]))
    assert response.status_code == 302

    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS
    assert campaign.is_in_progress
    assert not campaign.can_reopen_campaign()
    assert campaign.can_end_campaign()

    # Verify no new lists were cloned
    assert campaign.lists.count() == lists_before

    # Check that the campaign detail page shows "End" button again
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert b"End" in response.content
    assert b"bi-stop-circle" in response.content


@pytest.mark.django_db
def test_campaign_reopen_button_display(client):
    """Test that the reopen button is displayed correctly for ended campaigns."""
    user = User.objects.create_user(username="testuser", password="password")
    client.login(username="testuser", password="password")

    # Create a post-campaign
    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Ended Campaign",
        owner=user,
        status=Campaign.POST_CAMPAIGN,
        public=True,
    )

    # Check that the reopen button is shown on campaign detail page
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    assert b"Reopen" in response.content
    assert b"bi-arrow-clockwise" in response.content


@pytest.mark.django_db
def test_campaign_reopen_permissions(client):
    """Test that only the owner can reopen a campaign."""
    owner = User.objects.create_user(username="owner", password="password")
    User.objects.create_user(username="other", password="password")

    campaign = Campaign.objects.create_with_user(
        user=owner,
        name="Test Campaign",
        owner=owner,
        status=Campaign.POST_CAMPAIGN,
    )

    # Try to reopen campaign as non-owner
    client.login(username="other", password="password")
    response = client.post(reverse("core:campaign-reopen", args=[campaign.id]))
    assert response.status_code == 404  # Should not find campaign for non-owner

    campaign.refresh_from_db()
    assert campaign.status == Campaign.POST_CAMPAIGN  # Status unchanged

    # Reopen campaign as owner
    client.login(username="owner", password="password")
    response = client.post(reverse("core:campaign-reopen", args=[campaign.id]))
    assert response.status_code == 302

    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS


@pytest.mark.django_db
def test_campaign_status_permissions(client):
    """Test that only the owner can change campaign status."""
    owner = User.objects.create_user(username="owner", password="password")
    User.objects.create_user(username="other", password="password")

    # Create a house
    house = ContentHouse.objects.create(
        name="Test House",
    )

    campaign = Campaign.objects.create_with_user(
        user=owner,
        name="Test Campaign",
        owner=owner,
    )

    # Add a list so we can start the campaign
    list_obj = List.objects.create_with_user(
        user=owner,
        name="Test List",
        owner=owner,
        content_house=house,
    )
    campaign.lists.add(list_obj)

    # Try to start campaign as non-owner
    client.login(username="other", password="password")
    response = client.post(reverse("core:campaign-start", args=[campaign.id]))
    assert response.status_code == 404  # Should not find campaign for non-owner

    campaign.refresh_from_db()
    assert campaign.status == Campaign.PRE_CAMPAIGN  # Status unchanged

    # Start campaign as owner
    client.login(username="owner", password="password")
    response = client.post(reverse("core:campaign-start", args=[campaign.id]))
    assert response.status_code == 302

    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS


@pytest.mark.django_db
def test_campaign_status_display(client):
    """Test that campaign status is displayed correctly."""
    user = User.objects.create_user(username="testuser", password="password")
    client.login(username="testuser", password="password")

    # Create a house
    house = ContentHouse.objects.create(
        name="Test House",
    )

    # Create campaigns in different states
    pre_campaign = Campaign.objects.create_with_user(
        user=user,
        name="Pre Campaign",
        owner=user,
        status=Campaign.PRE_CAMPAIGN,
        public=True,
    )

    in_progress = Campaign.objects.create_with_user(
        user=user,
        name="Active Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
        public=True,
    )

    post_campaign = Campaign.objects.create_with_user(
        user=user,
        name="Finished Campaign",
        owner=user,
        status=Campaign.POST_CAMPAIGN,
        public=True,
    )

    # Check campaigns list page
    response = client.get(reverse("core:campaigns"))
    assert response.status_code == 200
    assert b"Pre-Campaign" in response.content
    assert b"In Progress" in response.content
    assert b"Post-Campaign" in response.content

    # Check individual campaign pages
    response = client.get(reverse("core:campaign", args=[pre_campaign.id]))
    assert response.status_code == 200
    assert b"Pre-Campaign" in response.content
    assert b"bi-play-circle" not in response.content  # No lists yet, so no start button

    # Add a list to pre_campaign
    list_obj = List.objects.create_with_user(
        user=user,
        name="Test List",
        owner=user,
        content_house=house,
    )
    pre_campaign.lists.add(list_obj)

    response = client.get(reverse("core:campaign", args=[pre_campaign.id]))
    assert b"Start" in response.content
    assert b"bi-play-circle" in response.content  # Check for the start icon

    response = client.get(reverse("core:campaign", args=[in_progress.id]))
    assert b"In Progress" in response.content
    assert b"End" in response.content
    assert b"bi-stop-circle" in response.content  # Check for the end icon

    response = client.get(reverse("core:campaign", args=[post_campaign.id]))
    assert b"Post-Campaign" in response.content
    assert b"bi-play-circle" not in response.content  # No start button
    assert b"bi-stop-circle" not in response.content  # No end button


@pytest.mark.django_db
def test_campaign_status_invalid_transitions(client):
    """Test that invalid status transitions are handled correctly."""
    user = User.objects.create_user(username="testuser", password="password")
    client.login(username="testuser", password="password")

    # Create campaigns in different states
    campaign_no_lists = Campaign.objects.create_with_user(
        user=user,
        name="Campaign No Lists",
        owner=user,
        status=Campaign.PRE_CAMPAIGN,
    )

    campaign_ended = Campaign.objects.create_with_user(
        user=user,
        name="Ended Campaign",
        owner=user,
        status=Campaign.POST_CAMPAIGN,
    )

    # Try to access start page for campaign without lists - should redirect
    response = client.get(reverse("core:campaign-start", args=[campaign_no_lists.id]))
    assert response.status_code == 302
    assert response.url == reverse("core:campaign", args=[campaign_no_lists.id])

    # Try to access end page for post-campaign - should redirect
    response = client.get(reverse("core:campaign-end", args=[campaign_ended.id]))
    assert response.status_code == 302
    assert response.url == reverse("core:campaign", args=[campaign_ended.id])


@pytest.mark.django_db
def test_campaign_post_campaign_restrictions(client):
    """Test that post-campaign campaigns cannot have lists added."""
    user = User.objects.create_user(username="testuser", password="password")
    client.login(username="testuser", password="password")

    # Create a house
    house = ContentHouse.objects.create(
        name="Test House",
    )

    # Create a post-campaign
    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Ended Campaign",
        owner=user,
        status=Campaign.POST_CAMPAIGN,
    )

    # Try to access add lists page - should redirect
    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))
    assert response.status_code == 302
    assert response.url == reverse("core:campaign", args=[campaign.id])

    # Check that the campaign detail page doesn't show "Add Lists" button
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    assert b"Add Lists" not in response.content

    # Create a list and try to add it via POST
    list_obj = List.objects.create_with_user(
        user=user,
        name="Test List",
        owner=user,
        content_house=house,
    )

    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]),
        data={"list_id": str(list_obj.id)},
    )
    assert response.status_code == 302
    assert response.url == reverse("core:campaign", args=[campaign.id])

    # Verify list was not added
    campaign.refresh_from_db()
    assert campaign.lists.count() == 0

    # Test that pre-campaign and in-progress campaigns CAN add lists
    pre_campaign = Campaign.objects.create_with_user(
        user=user,
        name="Pre Campaign",
        owner=user,
        status=Campaign.PRE_CAMPAIGN,
    )

    # Should be able to access add lists page
    response = client.get(reverse("core:campaign-add-lists", args=[pre_campaign.id]))
    assert response.status_code == 200

    # Check that the button is shown
    response = client.get(reverse("core:campaign", args=[pre_campaign.id]))
    assert b"Add Gangs" in response.content


@pytest.mark.django_db
def test_campaign_state_change_actions(client):
    """Test that campaign state changes create CampaignAction entries."""
    user = User.objects.create_user(username="testuser", password="password")
    client.login(username="testuser", password="password")

    # Create a house
    house = ContentHouse.objects.create(
        name="Test House",
    )

    # Create a campaign
    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Test Campaign",
        owner=user,
    )

    # Add a list so we can start the campaign
    list_obj = List.objects.create_with_user(
        user=user,
        name="Test List",
        owner=user,
        content_house=house,
    )
    campaign.lists.add(list_obj)

    # Verify no actions exist yet
    assert CampaignAction.objects.filter(campaign=campaign).count() == 0

    # Start the campaign
    response = client.post(reverse("core:campaign-start", args=[campaign.id]))
    assert response.status_code == 302

    # Verify campaign started and action was created
    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS

    start_actions = CampaignAction.objects.filter(campaign=campaign)
    assert start_actions.count() == 1
    start_action = start_actions.first()
    assert start_action.user == user
    assert start_action.description == "Campaign Started: Test Campaign is now active"
    assert (
        start_action.outcome
        == "Campaign transitioned from pre-campaign to active status"
    )

    # End the campaign
    response = client.post(reverse("core:campaign-end", args=[campaign.id]))
    assert response.status_code == 302

    # Verify campaign ended and action was created
    campaign.refresh_from_db()
    assert campaign.status == Campaign.POST_CAMPAIGN

    end_actions = CampaignAction.objects.filter(campaign=campaign).exclude(
        id=start_action.id
    )
    assert end_actions.count() == 1
    end_action = end_actions.first()
    assert end_action.user == user
    assert end_action.description == "Campaign Ended: Test Campaign has concluded"
    assert (
        end_action.outcome
        == "Campaign transitioned from active to post-campaign status"
    )

    # Reopen the campaign
    response = client.post(reverse("core:campaign-reopen", args=[campaign.id]))
    assert response.status_code == 302

    # Verify campaign reopened and action was created
    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS

    reopen_actions = CampaignAction.objects.filter(campaign=campaign).exclude(
        id__in=[start_action.id, end_action.id]
    )
    assert reopen_actions.count() == 1
    reopen_action = reopen_actions.first()
    assert reopen_action.user == user
    assert (
        reopen_action.description == "Campaign Reopened: Test Campaign is active again"
    )
    assert (
        reopen_action.outcome
        == "Campaign transitioned from post-campaign back to active status"
    )

    # Verify total actions count
    assert CampaignAction.objects.filter(campaign=campaign).count() == 3
