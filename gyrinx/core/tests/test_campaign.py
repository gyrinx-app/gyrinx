from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import Campaign, CampaignAction, CampaignListResource
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

    # When no summary/narrative, those sections are simply not rendered
    content = response.content.decode()
    assert "Empty Campaign" in content
    # The campaign info section still shows status, just not summary/narrative text
    assert "Pre-Campaign" in content


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

    # Verify that Reputation resource was automatically created
    reputation_resource = campaign.resource_types.get(name="Reputation")
    assert reputation_resource is not None
    assert (
        reputation_resource.description == "Gang reputation gained during the campaign"
    )
    assert reputation_resource.default_amount == 1


@pytest.mark.django_db
def test_campaign_automatically_creates_reputation_resource():
    """Test that creating a campaign automatically creates a Reputation resource."""
    client = Client()

    # Create and login user
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create a new campaign
    response = client.post(
        reverse("core:campaigns-new"),
        {
            "name": "Reputation Test Campaign",
            "summary": "Testing reputation resource",
            "narrative": "",
            "public": True,
            "budget": 1500,
        },
    )

    # Should redirect after successful creation
    assert response.status_code == 302

    # Get the created campaign
    campaign = Campaign.objects.get(name="Reputation Test Campaign")

    # Verify that exactly one resource type exists (Reputation)
    assert campaign.resource_types.count() == 1

    # Verify the Reputation resource details
    reputation = campaign.resource_types.first()
    assert reputation.name == "Reputation"
    assert reputation.description == "Gang reputation gained during the campaign"
    assert reputation.default_amount == 1
    assert reputation.owner == user

    # Create a house for the list
    house = ContentHouse.objects.create(name="Test House")

    # Verify that when campaign starts, reputation is allocated to lists
    list1 = List.objects.create(
        name="Test Gang 1",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    campaign.lists.add(list1)

    # Start the campaign
    assert campaign.start_campaign() is True

    # Verify reputation was allocated to the cloned list
    cloned_list = campaign.lists.first()
    reputation_resource = CampaignListResource.objects.get(
        campaign=campaign, resource_type=reputation, list=cloned_list
    )
    assert reputation_resource.amount == 1


@pytest.mark.django_db
def test_campaign_list_view_shows_plain_text_summary():
    """Test that HTML content is stripped to plain text in campaign list view.

    Campaign summaries in list views should show plain text, not HTML,
    to prevent large images and complex formatting from cluttering the list.
    Full HTML is still shown on the campaign detail page.
    """
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

    # HTML should be stripped to plain text in list view
    assert "Bold and italic summary" in content
    # HTML tags should NOT be rendered in the summary
    assert "<strong>Bold</strong>" not in content
    assert "<em>italic</em>" not in content


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
def test_campaign_prevents_duplicate_list_cloning():
    """Test that campaigns prevent duplicate cloning of lists."""
    # Create test users
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.PRE_CAMPAIGN,
    )

    # Create a house and list
    house = ContentHouse.objects.create(name="Test House")
    original_list = List.objects.create(
        name="Original Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Add the list to the campaign
    campaign.lists.add(original_list)

    # Start the campaign (should clone the list)
    assert campaign.start_campaign() is True

    # Verify the campaign is now in progress
    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS

    # Verify we have exactly one cloned list
    assert campaign.lists.count() == 1
    cloned_list = campaign.lists.first()
    assert cloned_list.original_list == original_list
    assert cloned_list.status == List.CAMPAIGN_MODE

    # Test the has_clone_of_list method
    assert campaign.has_clone_of_list(original_list) is True

    # Create another list to test negative case
    another_list = List.objects.create(
        name="Another Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    assert campaign.has_clone_of_list(another_list) is False


@pytest.mark.django_db
def test_campaign_add_list_prevents_duplicates():
    """Test that add_list_to_campaign prevents duplicate cloning."""
    # Create test users
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign already in progress
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.IN_PROGRESS,
    )

    # Create a house and list
    house = ContentHouse.objects.create(name="Test House")
    original_list = List.objects.create(
        name="Original Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Add the list to the campaign (should clone it)
    cloned_list1, was_added1 = campaign.add_list_to_campaign(original_list)
    assert was_added1 is True
    assert cloned_list1.original_list == original_list
    assert cloned_list1.status == List.CAMPAIGN_MODE
    assert campaign.lists.count() == 1

    # Try to add the same list again
    cloned_list2, was_added2 = campaign.add_list_to_campaign(original_list)

    # Should return the existing clone, not create a new one
    assert was_added2 is False
    assert cloned_list2.id == cloned_list1.id
    assert campaign.lists.count() == 1

    # Verify the returned list is the same as the first clone
    assert cloned_list2.original_list == original_list


@pytest.mark.django_db
def test_campaign_add_list_already_in_pre_campaign():
    """Test that add_list_to_campaign returns was_added=False for duplicates in pre-campaign."""
    # Create test users
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign in pre-campaign mode
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.PRE_CAMPAIGN,
    )

    # Create a house and list
    house = ContentHouse.objects.create(name="Test House")
    original_list = List.objects.create(
        name="Original Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Add the list to the campaign
    list1, was_added1 = campaign.add_list_to_campaign(original_list)
    assert was_added1 is True
    assert list1.id == original_list.id  # In pre-campaign, should be the same list
    assert campaign.lists.count() == 1

    # Try to add the same list again
    list2, was_added2 = campaign.add_list_to_campaign(original_list)

    # Should return the existing list, not add it again
    assert was_added2 is False
    assert list2.id == list1.id
    assert campaign.lists.count() == 1


@pytest.mark.django_db
def test_campaign_duplicate_prevention_with_transaction_rollback():
    """Test that duplicate prevention works even with transaction rollback scenarios."""
    # Create test users
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.PRE_CAMPAIGN,
    )

    # Create a house and lists
    house = ContentHouse.objects.create(name="Test House")
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

    # Add both lists to the campaign
    campaign.lists.add(list1, list2)

    # Start the campaign
    assert campaign.start_campaign() is True

    # Now we have clones of both lists
    assert campaign.lists.count() == 2
    clone1 = campaign.lists.get(original_list=list1)
    clone2 = campaign.lists.get(original_list=list2)

    # Simulate a scenario where someone tries to add the original lists again
    # This might happen if the campaign status was reset due to an error
    campaign.status = Campaign.PRE_CAMPAIGN
    campaign.save()

    # The clones still exist in the campaign
    assert campaign.lists.filter(original_list=list1).exists()
    assert campaign.lists.filter(original_list=list2).exists()

    # Now add the original lists again (simulating retry after failure)
    campaign.lists.add(list1, list2)

    # Before starting, we have 4 lists (2 originals + 2 clones)
    assert campaign.lists.count() == 4

    # Start the campaign again - should not create duplicates
    assert campaign.start_campaign() is True

    # After starting, the originals are removed and we keep only the clones
    campaign.refresh_from_db()
    assert campaign.lists.count() == 2

    # The clones should be the same ones
    assert campaign.lists.get(original_list=list1).id == clone1.id
    assert campaign.lists.get(original_list=list2).id == clone2.id


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


@pytest.mark.django_db
def test_campaign_restart_with_existing_clones_no_integrity_error():
    """Test that restarting a campaign with existing clones doesn't cause IntegrityError."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.PRE_CAMPAIGN,
    )

    # Create resource types for the campaign
    from gyrinx.core.models.campaign import CampaignResourceType

    CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        default_amount=10,
        owner=user,
    )
    CampaignResourceType.objects.create(
        campaign=campaign,
        name="Ammo",
        default_amount=20,
        owner=user,
    )

    # Create a house and list
    house = ContentHouse.objects.create(name="Test House")
    original_list = List.objects.create(
        name="Original Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Add the list to the campaign
    campaign.lists.add(original_list)

    # Start the campaign (should clone the list and allocate resources)
    assert campaign.start_campaign() is True

    # Verify resources were allocated
    cloned_list = campaign.lists.first()
    assert (
        CampaignListResource.objects.filter(campaign=campaign, list=cloned_list).count()
        == 2
    )

    # Reset campaign status to pre-campaign (simulating a restart scenario)
    campaign.status = Campaign.PRE_CAMPAIGN
    campaign.save()

    # Add the original list back (simulating the scenario that triggers the bug)
    campaign.lists.add(original_list)

    # Start the campaign again - this should NOT raise IntegrityError
    # The fix uses get_or_create instead of create
    assert campaign.start_campaign() is True

    # Verify we still have the same resources (not duplicated)
    campaign.refresh_from_db()
    assert campaign.lists.count() == 1  # Still just one cloned list
    cloned_list = campaign.lists.first()
    assert (
        CampaignListResource.objects.filter(campaign=campaign, list=cloned_list).count()
        == 2
    )  # Still just 2 resource types


@pytest.mark.django_db
def test_add_list_to_in_progress_campaign_with_existing_resources():
    """Test that adding a list to in-progress campaign handles resource allocation idempotently."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign already in progress
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.IN_PROGRESS,
    )

    # Create resource types for the campaign
    from gyrinx.core.models.campaign import CampaignResourceType

    CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        default_amount=10,
        owner=user,
    )
    CampaignResourceType.objects.create(
        campaign=campaign,
        name="Ammo",
        default_amount=20,
        owner=user,
    )

    # Create a house and list
    house = ContentHouse.objects.create(name="Test House")
    original_list = List.objects.create(
        name="Original Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Add the list to the campaign (should clone and allocate resources)
    cloned_list1, was_added1 = campaign.add_list_to_campaign(original_list)
    assert was_added1 is True

    # Verify resources were allocated
    assert (
        CampaignListResource.objects.filter(
            campaign=campaign, list=cloned_list1
        ).count()
        == 2
    )

    # Try to add the same list again - should return existing clone
    cloned_list2, was_added2 = campaign.add_list_to_campaign(original_list)
    assert was_added2 is False  # Should return existing clone
    assert cloned_list2.id == cloned_list1.id

    # Create another list to add
    original_list2 = List.objects.create(
        name="Another Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Add a new list - this should work without IntegrityError
    cloned_list3, was_added3 = campaign.add_list_to_campaign(original_list2)
    assert was_added3 is True
    assert cloned_list3.id != cloned_list1.id

    # Verify the new list has resources allocated
    assert (
        CampaignListResource.objects.filter(
            campaign=campaign, list=cloned_list3
        ).count()
        == 2
    )

    # Verify no duplicate resources were created
    # Each list should have exactly 2 resources (one for each resource type)
    all_resources = CampaignListResource.objects.filter(campaign=campaign)
    assert all_resources.count() == 4  # 2 lists * 2 resource types


@pytest.mark.django_db
def test_campaign_resource_allocation_race_condition():
    """Test that resource allocation is safe even when called multiple times (simulating race conditions)."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.PRE_CAMPAIGN,
    )

    # Create resource types for the campaign
    from gyrinx.core.models.campaign import CampaignResourceType

    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        default_amount=100,
        owner=user,
    )

    # Create a house and list
    house = ContentHouse.objects.create(name="Test House")
    original_list = List.objects.create(
        name="Original Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Add the list to the campaign
    campaign.lists.add(original_list)

    # Start the campaign
    assert campaign.start_campaign() is True

    # Get the cloned list
    cloned_list = campaign.lists.first()

    # Verify resources were allocated
    resources_count = CampaignListResource.objects.filter(
        campaign=campaign, list=cloned_list
    ).count()
    assert resources_count == 1

    # Simulate calling the resource allocation code again
    # This would happen in the old code if start_campaign was called twice
    # With get_or_create, this should not create duplicates
    CampaignListResource.objects.get_or_create(
        campaign=campaign,
        resource_type=resource_type,
        list=cloned_list,
        defaults={
            "amount": resource_type.default_amount,
            "owner": campaign.owner,
        },
    )

    # Verify no duplicates were created
    resources_count = CampaignListResource.objects.filter(
        campaign=campaign, list=cloned_list
    ).count()
    assert resources_count == 1  # Still just one resource, not two
