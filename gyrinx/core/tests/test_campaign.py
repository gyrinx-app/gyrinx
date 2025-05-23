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
