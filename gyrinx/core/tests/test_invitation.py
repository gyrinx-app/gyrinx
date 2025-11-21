import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.core.models import Campaign, CampaignInvitation, List
from gyrinx.content.models import ContentHouse

User = get_user_model()


@pytest.fixture
def campaign_owner(db):
    """Create a user who owns a campaign."""
    return User.objects.create_user(username="campaign_owner", password="password123")


@pytest.fixture
def list_owner(db):
    """Create a user who owns a list."""
    return User.objects.create_user(username="list_owner", password="password123")


@pytest.fixture
def house(db):
    """Create a content house."""
    return ContentHouse.objects.create(name="Test House")


@pytest.fixture
def campaign(campaign_owner):
    """Create a campaign."""
    return Campaign.objects.create(
        name="Test Campaign",
        owner=campaign_owner,
        status=Campaign.PRE_CAMPAIGN,
    )


@pytest.fixture
def test_list(list_owner, house):
    """Create a list."""
    return List.objects.create(
        name="Test List",
        owner=list_owner,
        content_house=house,
        status=List.LIST_BUILDING,
        public=True,
    )


@pytest.mark.django_db
def test_create_invitation(campaign, test_list, campaign_owner):
    """Test creating a campaign invitation."""
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )

    assert invitation.status == CampaignInvitation.PENDING
    assert invitation.campaign == campaign
    assert invitation.list == test_list
    assert invitation.is_pending is True
    assert invitation.is_accepted is False
    assert invitation.is_declined is False


@pytest.mark.django_db
def test_accept_invitation(campaign, test_list, campaign_owner):
    """Test accepting a campaign invitation."""
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )

    result = invitation.accept()

    assert result is True
    assert invitation.status == CampaignInvitation.ACCEPTED
    assert invitation.is_accepted is True
    assert test_list in campaign.lists.all()


@pytest.mark.django_db
def test_decline_invitation(campaign, test_list, campaign_owner):
    """Test declining a campaign invitation."""
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )

    result = invitation.decline()

    assert result is True
    assert invitation.status == CampaignInvitation.DECLINED
    assert invitation.is_declined is True
    assert test_list not in campaign.lists.all()


@pytest.mark.django_db
def test_cannot_accept_non_pending_invitation(campaign, test_list, campaign_owner):
    """Test that non-pending invitations cannot be accepted."""
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )
    invitation.decline()

    result = invitation.accept()

    assert result is False
    assert invitation.status == CampaignInvitation.DECLINED


@pytest.mark.django_db
def test_cannot_decline_non_pending_invitation(campaign, test_list, campaign_owner):
    """Test that non-pending invitations cannot be declined."""
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )
    invitation.accept()

    result = invitation.decline()

    assert result is False
    assert invitation.status == CampaignInvitation.ACCEPTED


@pytest.mark.django_db
def test_unique_invitation_per_campaign_list(campaign, test_list, campaign_owner):
    """Test that only one invitation can exist per campaign-list combination."""
    CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )

    with pytest.raises(Exception):  # IntegrityError
        CampaignInvitation.objects.create(
            campaign=campaign, list=test_list, owner=campaign_owner
        )


@pytest.mark.django_db
def test_list_invitations_view(client, list_owner, test_list, campaign, campaign_owner):
    """Test the list invitations view."""
    # Create an invitation
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )

    # Login as list owner
    client.login(username="list_owner", password="password123")

    # Access the invitations page
    url = reverse("core:list-invitations", args=[test_list.id])
    response = client.get(url)

    assert response.status_code == 200
    assert invitation in response.context["invitations"]
    assert b"Test Campaign" in response.content


@pytest.mark.django_db
def test_accept_invitation_view(
    client, list_owner, test_list, campaign, campaign_owner
):
    """Test accepting an invitation through the view."""
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )

    # Login as list owner
    client.login(username="list_owner", password="password123")

    # Accept the invitation
    url = reverse("core:invitation-accept", args=[test_list.id, invitation.id])
    response = client.post(url)

    # Check redirect
    assert response.status_code == 302

    # Verify invitation was accepted
    invitation.refresh_from_db()
    assert invitation.status == CampaignInvitation.ACCEPTED
    assert test_list in campaign.lists.all()


@pytest.mark.django_db
def test_decline_invitation_view(
    client, list_owner, test_list, campaign, campaign_owner
):
    """Test declining an invitation through the view."""
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )

    # Login as list owner
    client.login(username="list_owner", password="password123")

    # Decline the invitation
    url = reverse("core:invitation-decline", args=[test_list.id, invitation.id])
    response = client.post(url)

    # Check redirect
    assert response.status_code == 302

    # Verify invitation was declined
    invitation.refresh_from_db()
    assert invitation.status == CampaignInvitation.DECLINED
    assert test_list not in campaign.lists.all()


@pytest.mark.django_db
def test_campaign_add_lists_creates_invitations(
    client, campaign_owner, list_owner, test_list, campaign, house
):
    """Test that the campaign_add_lists view creates invitations instead of directly adding lists."""
    # Login as campaign owner
    client.login(username="campaign_owner", password="password123")

    # Try to add a list
    url = reverse("core:campaign-add-lists", args=[campaign.id])
    response = client.post(url, {"list_id": test_list.id})

    # Check redirect
    assert response.status_code == 302

    # Verify invitation was created
    invitation = CampaignInvitation.objects.get(campaign=campaign, list=test_list)
    assert invitation.status == CampaignInvitation.PENDING

    # List should not be directly added
    assert test_list not in campaign.lists.all()


@pytest.mark.django_db
def test_resend_declined_invitation(client, campaign_owner, test_list, campaign):
    """Test that declined invitations can be re-sent."""
    # Create and decline an invitation
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )
    invitation.decline()

    # Login as campaign owner
    client.login(username="campaign_owner", password="password123")

    # Try to add the list again
    url = reverse("core:campaign-add-lists", args=[campaign.id])
    response = client.post(url, {"list_id": test_list.id})

    # Check redirect
    assert response.status_code == 302

    # Verify invitation was reset to pending
    invitation.refresh_from_db()
    assert invitation.status == CampaignInvitation.PENDING


@pytest.mark.django_db
def test_list_detail_shows_invitation_count(
    client, list_owner, test_list, campaign, campaign_owner
):
    """Test that the list detail view shows pending invitation count."""
    # Create an invitation
    CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )

    # Login as list owner
    client.login(username="list_owner", password="password123")

    # Access the list detail page
    url = reverse("core:list", args=[test_list.id])
    response = client.get(url)

    assert response.status_code == 200
    assert response.context["pending_invitations_count"] == 1


@pytest.mark.django_db
def test_campaign_add_lists_auto_accept_same_owner(
    client, campaign_owner, test_list, campaign
):
    """Test that adding a list owned by the campaign owner auto-accepts."""
    # Ensure campaign owner owns the list
    test_list.owner = campaign_owner
    test_list.save()

    # Login as campaign owner
    client.login(username="campaign_owner", password="password123")

    # Add the list
    url = reverse("core:campaign-add-lists", args=[campaign.id])
    response = client.post(url, {"list_id": test_list.id})

    # Check redirect
    assert response.status_code == 302

    # Verify invitation was created and ACCEPTED
    invitation = CampaignInvitation.objects.get(campaign=campaign, list=test_list)
    assert invitation.status == CampaignInvitation.ACCEPTED

    # Verify list is in campaign
    assert test_list in campaign.lists.all()

    # Verify message
    messages = list(response.wsgi_request._messages)
    assert len(messages) == 1
    assert str(messages[0]) == f"{test_list.name} has been added to the campaign."


@pytest.mark.django_db
def test_resend_declined_invitation_auto_accept_same_owner(
    client, campaign_owner, test_list, campaign
):
    """Test that re-sending a declined invitation auto-accepts if owners match."""
    # Ensure campaign owner owns the list
    test_list.owner = campaign_owner
    test_list.save()

    # Create and decline an invitation
    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=test_list, owner=campaign_owner
    )
    invitation.decline()

    # Login as campaign owner
    client.login(username="campaign_owner", password="password123")

    # Add the list again
    url = reverse("core:campaign-add-lists", args=[campaign.id])
    response = client.post(url, {"list_id": test_list.id})

    # Check redirect
    assert response.status_code == 302

    # Verify invitation is now ACCEPTED
    invitation.refresh_from_db()
    assert invitation.status == CampaignInvitation.ACCEPTED

    # Verify list is in campaign
    assert test_list in campaign.lists.all()
