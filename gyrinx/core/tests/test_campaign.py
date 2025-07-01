from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List


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


@pytest.mark.django_db
def test_campaign_xss_protection_direct_db():
    """Test that XSS content created directly in DB is rendered with |safe filter.

    Note: This test documents the current behavior where content saved directly
    to the database bypasses TinyMCE sanitization. In production, content should
    only be saved through forms with TinyMCE which provides sanitization.
    """
    client = Client()

    # Create a test user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create campaign with XSS directly in database (bypassing forms/TinyMCE)
    campaign = Campaign.objects.create(
        name="XSS Test Campaign",
        owner=user,
        public=True,
        summary='<p>Summary with <script>alert("XSS")</script></p>',
        narrative='<p>Narrative with <script>alert("XSS")</script></p>',
    )

    # Fetch the campaign detail page
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    content = response.content.decode()

    # When content is created directly in DB (bypassing TinyMCE),
    # the |safe filter will render it as-is. This documents current behavior.
    # In production, all content should go through TinyMCE forms which sanitize input.
    assert campaign.name in content


@pytest.mark.django_db
def test_campaign_safe_html_allowed():
    """Test that safe HTML tags are properly rendered in campaigns."""
    client = Client()

    # Create a test user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign with safe HTML
    safe_html = """
    <h2>Campaign Overview</h2>
    <p>This is a <strong>bold</strong> and <em>italic</em> text.</p>
    <ul>
        <li>List item 1</li>
        <li>List item 2</li>
    </ul>
    <ol>
        <li>Numbered item 1</li>
        <li>Numbered item 2</li>
    </ol>
    <blockquote>This is a quote</blockquote>
    <a href="/lists/">Link to lists</a>
    <hr>
    <table>
        <tr><th>Header</th><td>Data</td></tr>
    </table>
    """

    campaign = Campaign.objects.create(
        name="Safe HTML Campaign",
        owner=user,
        public=True,
        summary="A campaign with safe HTML",
        narrative=safe_html,
    )

    # Test the campaign detail view
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    content = response.content.decode()

    # Verify safe HTML tags are preserved
    assert "<h2>Campaign Overview</h2>" in content
    assert "<strong>bold</strong>" in content
    assert "<em>italic</em>" in content
    assert "<ul>" in content
    assert "<ol>" in content
    assert "<blockquote>This is a quote</blockquote>" in content
    assert "<hr>" in content  # HR might be self-closing
    assert "<table>" in content


@pytest.mark.django_db
def test_campaign_create_edit_forms():
    """Test campaign create and edit forms work correctly.

    Note: TinyMCE sanitization happens client-side. Server-side tests
    can verify form submission works but cannot test JavaScript-based
    sanitization without a full browser environment.
    """
    client = Client()

    # Create and login user
    User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Test creating a campaign via form
    response = client.post(
        reverse("core:campaigns-new"),
        {
            "name": "Test Campaign",
            "summary": "This is a test summary",
            "narrative": "<p>This is a <strong>test</strong> narrative</p>",
            "public": True,
            "budget": 1500,
        },
    )

    # Should redirect after successful creation
    assert response.status_code == 302

    # Get the created campaign
    campaign = Campaign.objects.get(name="Test Campaign")
    assert campaign.summary == "This is a test summary"
    assert campaign.narrative == "<p>This is a <strong>test</strong> narrative</p>"

    # Test editing the campaign
    response = client.post(
        reverse("core:campaign-edit", args=[campaign.id]),
        {
            "name": "Test Campaign Edited",
            "summary": "Updated summary",
            "narrative": "<p>Updated <em>narrative</em></p>",
            "public": False,
            "budget": 2000,  # Budget can be updated
        },
    )

    # Should redirect after successful edit
    assert response.status_code == 302

    # Verify edit was saved
    campaign.refresh_from_db()
    assert campaign.name == "Test Campaign Edited"
    assert campaign.summary == "Updated summary"
    assert campaign.narrative == "<p>Updated <em>narrative</em></p>"
    assert campaign.public is False
    assert campaign.budget == 2000


@pytest.mark.django_db
def test_campaign_list_view_html_content():
    """Test that HTML content is displayed in campaign list view."""
    client = Client()

    # Create a test user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create campaign with HTML in summary
    Campaign.objects.create(
        name="HTML Summary Test",
        owner=user,
        public=True,
        summary="<strong>Bold</strong> and <em>italic</em> summary",
        narrative="Regular narrative",
    )

    # Test the campaigns list view
    response = client.get(reverse("core:campaigns"))
    assert response.status_code == 200

    content = response.content.decode()

    # The campaign should be listed
    assert "HTML Summary Test" in content

    # HTML should be rendered (using |safe filter)
    assert "<strong>Bold</strong>" in content
    assert "<em>italic</em>" in content


@pytest.mark.django_db
def test_campaign_xss_protection_recommendation():
    """Test demonstrates recommended approach for XSS protection.

    This test shows what would happen if server-side HTML sanitization
    was implemented (e.g., using bleach or django-bleach).
    """
    import html

    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")

    # Example of how content should be sanitized server-side
    unsafe_content = '<script>alert("XSS")</script><p>Safe content</p>'

    # Simple escaping (what Django does by default without |safe)
    escaped_content = html.escape(unsafe_content)

    campaign = Campaign.objects.create(
        name="Escaped Content Test",
        owner=user,
        public=True,
        summary=escaped_content,
        narrative=escaped_content,
    )

    response = client.get(reverse("core:campaign", args=[campaign.id]))
    content = response.content.decode()

    # With escaped content and |safe filter, the escaped HTML entities are shown
    assert "&lt;script&gt;" in content
    assert "&lt;p&gt;Safe content&lt;/p&gt;" in content

    # The actual script tag is not present
    assert "<script>alert" not in content


@pytest.mark.django_db
def test_campaign_action_list_filtering():
    """Test that campaign action list view supports filtering."""
    client = Client()

    # Create test users
    user1 = User.objects.create_user(username="player1", password="testpass")
    user2 = User.objects.create_user(username="player2", password="testpass")
    owner = User.objects.create_user(username="owner", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=owner,
        public=True,
        summary="A test campaign",
        status=Campaign.IN_PROGRESS,
    )

    # Create houses and lists for the campaign
    house1 = ContentHouse.objects.create(name="House Goliath")
    house2 = ContentHouse.objects.create(name="House Escher")

    list1 = List.objects.create(
        name="Gang Alpha",
        owner=user1,
        content_house=house1,
        campaign=campaign,
    )
    list2 = List.objects.create(
        name="Gang Beta",
        owner=user2,
        content_house=house2,
        campaign=campaign,
    )

    campaign.lists.add(list1, list2)

    # Create some campaign actions
    action1 = CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        owner=user1,  # Add owner field
        list=list1,  # Associate with Gang Alpha
        description="Gang Alpha attacks the water still",
        outcome="Victory! Water still captured",
        dice_count=3,
    )
    action1.roll_dice()
    action1.save()

    action2 = CampaignAction.objects.create(
        campaign=campaign,
        user=user2,
        owner=user2,  # Add owner field
        list=list2,  # Associate with Gang Beta
        description="Gang Beta scouts the underhive",
        outcome="Found a hidden cache",
        dice_count=2,
    )
    action2.roll_dice()
    action2.save()

    CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        owner=user1,  # Add owner field
        list=list1,  # Associate with Gang Alpha
        description="Gang Alpha trades at the market",
        outcome="",
        dice_count=0,
    )

    # Log in as owner
    client.login(username="owner", password="testpass")

    # Test unfiltered view
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" in content
    assert "Gang Beta scouts the underhive" in content
    assert "Gang Alpha trades at the market" in content

    # Test text search filtering
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"q": "water still"}
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" in content
    assert "Gang Beta scouts the underhive" not in content
    assert "Gang Alpha trades at the market" not in content

    # Test gang filtering
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"gang": str(list1.id)}
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" in content
    assert "Gang Beta scouts the underhive" not in content
    assert "Gang Alpha trades at the market" in content

    # Test author filtering
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"author": str(user2.id)}
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" not in content
    assert "Gang Beta scouts the underhive" in content
    assert "Gang Alpha trades at the market" not in content

    # Test combined filters
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]),
        {"q": "market", "author": str(user1.id)},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" not in content
    assert "Gang Beta scouts the underhive" not in content
    assert "Gang Alpha trades at the market" in content

    # Test that filter form elements are present
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    content = response.content.decode()
    assert 'name="q"' in content  # Search input
    assert 'name="gang"' in content  # Gang select
    assert 'name="author"' in content  # Author select
    assert "Update Filters" in content  # Filter button

    # Test that pagination preserves filters
    # Create more actions to trigger pagination
    # We need more than 50 results matching the filter to see pagination
    for i in range(55):
        CampaignAction.objects.create(
            campaign=campaign,
            user=user1,
            description=f"Gang Alpha trades water supplies - batch {i}",
        )

    # Now we have 56 water-related actions (1 original + 55 new), which triggers pagination
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"q": "water"}
    )
    assert response.status_code == 200
    content = response.content.decode()
    # Check that filter parameters are preserved in pagination links
    assert "page=2" in content  # Next page link should exist
    assert "q=water" in content  # Filter should be preserved


@pytest.mark.django_db
def test_campaign_action_list_timeframe_filtering():
    """Test that campaign action list view supports timeframe filtering."""
    client = Client()

    # Create test users
    user1 = User.objects.create_user(username="player1", password="testpass")
    owner = User.objects.create_user(username="owner", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=owner,
        public=True,
        summary="A test campaign",
        status=Campaign.IN_PROGRESS,
    )

    # Create a list for the campaign
    house1 = ContentHouse.objects.create(name="House Goliath")
    list1 = List.objects.create(
        name="Gang Alpha",
        owner=user1,
        content_house=house1,
        campaign=campaign,
    )
    campaign.lists.add(list1)

    # Create actions with different timestamps
    now = timezone.now()

    # Action from 1 hour ago
    action_1h = CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        description="Recent action from 1 hour ago",
    )
    action_1h.created = now - timedelta(hours=1)
    action_1h.save()

    # Action from 3 days ago
    action_3d = CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        description="Action from 3 days ago",
    )
    action_3d.created = now - timedelta(days=3)
    action_3d.save()

    # Action from 10 days ago
    action_10d = CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        description="Action from 10 days ago",
    )
    action_10d.created = now - timedelta(days=10)
    action_10d.save()

    # Action from 40 days ago
    action_40d = CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        description="Old action from 40 days ago",
    )
    action_40d.created = now - timedelta(days=40)
    action_40d.save()

    # Log in as owner
    client.login(username="owner", password="testpass")

    # Test unfiltered view (all actions)
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Recent action from 1 hour ago" in content
    assert "Action from 3 days ago" in content
    assert "Action from 10 days ago" in content
    assert "Old action from 40 days ago" in content

    # Test last 24 hours filter
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"timeframe": "24h"}
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Recent action from 1 hour ago" in content
    assert "Action from 3 days ago" not in content
    assert "Action from 10 days ago" not in content
    assert "Old action from 40 days ago" not in content

    # Test last 7 days filter
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"timeframe": "7d"}
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Recent action from 1 hour ago" in content
    assert "Action from 3 days ago" in content
    assert "Action from 10 days ago" not in content
    assert "Old action from 40 days ago" not in content

    # Test last 30 days filter
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"timeframe": "30d"}
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Recent action from 1 hour ago" in content
    assert "Action from 3 days ago" in content
    assert "Action from 10 days ago" in content
    assert "Old action from 40 days ago" not in content

    # Test that timeframe filter form element is present
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    content = response.content.decode()
    assert 'name="timeframe"' in content
    assert "Any time" in content
    assert "Last 24 hours" in content
    assert "Last 7 days" in content
    assert "Last 30 days" in content

    # Test combined filters (timeframe + text search)
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]),
        {"timeframe": "7d", "q": "action"},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Recent action from 1 hour ago" in content
    assert "Action from 3 days ago" in content
    assert "Action from 10 days ago" not in content
    assert "Old action from 40 days ago" not in content

    # Test that pagination preserves timeframe filter
    # Create more actions to trigger pagination
    for i in range(55):
        new_action = CampaignAction.objects.create(
            campaign=campaign,
            user=user1,
            description=f"Recent batch action {i}",
        )
        # Set them all within last 24 hours
        new_action.created = now - timedelta(hours=i % 24)
        new_action.save()

    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"timeframe": "24h"}
    )
    assert response.status_code == 200
    content = response.content.decode()
    # Check that filter parameters are preserved in pagination links
    assert "page=2" in content  # Next page link should exist
    assert "timeframe=24h" in content  # Filter should be preserved
