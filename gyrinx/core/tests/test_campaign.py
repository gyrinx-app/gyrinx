import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.core.models.campaign import Campaign


@pytest.mark.django_db
def test_campaign_list_view():
    """Test that the campaign list view returns campaigns."""
    client = Client()

    # Create a test user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create public and private campaigns
    public_campaign = Campaign.objects.create(
        name="Public Campaign",
        owner=user,
        public=True,
        summary="A public campaign summary",
    )
    Campaign.objects.create(
        name="Private Campaign",
        owner=user,
        public=False,
        summary="A private campaign summary",
    )

    # Test the campaign list view
    response = client.get(reverse("core:campaigns"))
    assert response.status_code == 200

    # Check that only public campaigns are shown
    assert "Public Campaign" in response.content.decode()
    assert "Private Campaign" not in response.content.decode()

    # Check that the link to the campaign detail is correct
    assert (
        f'href="{reverse("core:campaign", args=[public_campaign.id])}"'
        in response.content.decode()
    )


@pytest.mark.django_db
def test_campaign_detail_view():
    """Test that the campaign detail view shows campaign information."""
    client = Client()

    # Create a test user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign with HTML in narrative
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        summary="This is a test campaign summary.",
        narrative="<p>This is a longer narrative about the test campaign.</p>\n<p>It has <strong>HTML formatting</strong>.</p>",
    )

    # Test the campaign detail view
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    # Check that campaign details are shown and HTML is rendered
    content = response.content.decode()
    assert "Test Campaign" in content
    assert "This is a test campaign summary." in content
    assert "<p>This is a longer narrative about the test campaign.</p>" in content
    assert "<strong>HTML formatting</strong>" in content
    assert f'href="{reverse("core:user", args=[user.username])}"' in content
    assert user.username in content


@pytest.mark.django_db
def test_campaign_detail_view_no_content():
    """Test that the campaign detail view handles campaigns with no summary or narrative."""
    client = Client()

    # Create a test user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign with no content
    campaign = Campaign.objects.create(
        name="Empty Campaign", owner=user, public=True, summary="", narrative=""
    )

    # Test the campaign detail view
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    # Check that the no content message is shown
    content = response.content.decode()
    assert "No campaign details have been added yet." in content


@pytest.mark.django_db
def test_campaign_detail_view_404():
    """Test that the campaign detail view returns 404 for non-existent campaigns."""
    client = Client()

    # Try to access a non-existent campaign
    response = client.get(
        reverse("core:campaign", args=["00000000-0000-0000-0000-000000000000"])
    )
    assert response.status_code == 404
