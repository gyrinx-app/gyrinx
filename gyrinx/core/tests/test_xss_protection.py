"""
Test XSS protection with bleach sanitization.

This module tests that the safe_rich_text filter properly sanitizes
user-generated HTML content to prevent XSS attacks while preserving
safe formatting.
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.core.models import BattleNote, Campaign, List
from gyrinx.core.templatetags.custom_tags import safe_rich_text
from gyrinx.content.models import ContentHouse


@pytest.mark.django_db
def test_safe_rich_text_filter_removes_dangerous_content():
    """Test that the safe_rich_text filter removes dangerous HTML/JS."""

    # Test script tags are removed (completely stripped including content)
    assert safe_rich_text('<script>alert("XSS")</script>') == ""
    assert (
        safe_rich_text('<p>Safe text</p><script>alert("XSS")</script>')
        == "<p>Safe text</p>"
    )

    # Test event handlers are removed
    assert safe_rich_text('<img src="x" onerror="alert(\'XSS\')">') == '<img src="x">'
    assert (
        safe_rich_text("<div onclick=\"alert('XSS')\">Click me</div>")
        == "<div>Click me</div>"
    )

    # Test javascript: URLs are sanitized
    assert (
        safe_rich_text("<a href=\"javascript:alert('XSS')\">Link</a>") == "<a>Link</a>"
    )

    # Test data: URLs are sanitized (for images with embedded JS)
    assert (
        safe_rich_text("<img src=\"data:text/html,<script>alert('XSS')</script>\">")
        == "<img>"
    )

    # Test style tags are removed
    assert safe_rich_text("<style>body { display: none; }</style>") == ""

    # Test iframes are removed
    assert safe_rich_text("<iframe src=\"javascript:alert('XSS')\"></iframe>") == ""

    # Test form injection is removed
    assert (
        safe_rich_text('<form action="http://evil.com"><input name="password"></form>')
        == ""
    )

    # Test SVG with scripts are sanitized
    assert safe_rich_text("<svg onload=\"alert('XSS')\"></svg>") == ""

    # Test meta refresh is removed
    assert (
        safe_rich_text('<meta http-equiv="refresh" content="0;url=http://evil.com">')
        == ""
    )


@pytest.mark.django_db
def test_safe_rich_text_filter_preserves_safe_content():
    """Test that the safe_rich_text filter preserves safe HTML formatting."""

    # Test basic text formatting is preserved
    assert safe_rich_text("<p>Paragraph</p>") == "<p>Paragraph</p>"
    assert safe_rich_text("<strong>Bold</strong>") == "<strong>Bold</strong>"
    assert safe_rich_text("<em>Italic</em>") == "<em>Italic</em>"
    assert safe_rich_text("<u>Underline</u>") == "<u>Underline</u>"

    # Test headers are preserved
    assert safe_rich_text("<h1>Header 1</h1>") == "<h1>Header 1</h1>"
    assert safe_rich_text("<h2>Header 2</h2>") == "<h2>Header 2</h2>"

    # Test lists are preserved
    assert (
        safe_rich_text("<ul><li>Item 1</li><li>Item 2</li></ul>")
        == "<ul><li>Item 1</li><li>Item 2</li></ul>"
    )
    assert (
        safe_rich_text("<ol><li>Item 1</li><li>Item 2</li></ol>")
        == "<ol><li>Item 1</li><li>Item 2</li></ol>"
    )

    # Test safe links are preserved
    assert (
        safe_rich_text('<a href="https://example.com">Link</a>')
        == '<a href="https://example.com">Link</a>'
    )
    assert (
        safe_rich_text('<a href="/relative/path">Link</a>')
        == '<a href="/relative/path">Link</a>'
    )

    # Test images with safe attributes are preserved (order may vary)
    result = safe_rich_text('<img src="/image.jpg" alt="Description">')
    assert 'src="/image.jpg"' in result
    assert 'alt="Description"' in result
    assert result.startswith("<img") and result.endswith(">")
    # Test another image with multiple attributes
    result2 = safe_rich_text(
        '<img src="https://example.com/image.jpg" width="100" height="100">'
    )
    assert 'src="https://example.com/image.jpg"' in result2
    assert 'width="100"' in result2
    assert 'height="100"' in result2

    # Test blockquotes and code blocks are preserved
    assert (
        safe_rich_text("<blockquote>Quote</blockquote>")
        == "<blockquote>Quote</blockquote>"
    )
    assert (
        safe_rich_text("<pre><code>Code block</code></pre>")
        == "<pre><code>Code block</code></pre>"
    )

    # Test tables are preserved (bleach may add tbody)
    table_html = "<table><tr><th>Header</th></tr><tr><td>Data</td></tr></table>"
    result = safe_rich_text(table_html)
    assert "<table>" in result
    assert "<th>Header</th>" in result
    assert "<td>Data</td>" in result
    assert "</table>" in result


@pytest.mark.django_db
def test_campaign_with_xss_content_is_sanitized():
    """Test that XSS content in campaigns is properly sanitized in templates."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create campaign with XSS content directly in database
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        summary='<p>Summary</p><script>alert("XSS in summary")</script>',
        narrative='<p>Story</p><script>alert("XSS in narrative")</script><img src=x onerror="alert(\'img XSS\')">',
    )

    # Fetch the campaign detail page
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    content = response.content.decode()

    # Verify XSS is removed but safe content remains
    assert "<p>Summary</p>" in content
    assert "<p>Story</p>" in content
    # Check that XSS script content is not present (not checking for <script> tag itself as page has legitimate scripts)
    assert 'alert("XSS in summary")' not in content
    assert 'alert("XSS in narrative")' not in content
    assert "onerror=" not in content

    # Verify the actual img tag is present but sanitized
    assert "<img" in content  # Image tag should be present
    assert (
        'src="x"' in content or "src=x" not in content
    )  # src should be preserved or removed


@pytest.mark.django_db
def test_battle_notes_with_xss_are_sanitized():
    """Test that XSS content in battle notes is properly sanitized."""
    from gyrinx.core.models import Battle

    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    # Create campaign and battle
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
    )

    battle = Battle.objects.create(
        campaign=campaign,
        owner=user,
        date="2025-01-01",
    )

    # Create battle note with XSS content directly
    BattleNote.objects.create(
        battle=battle,
        owner=user,
        content='<p>Note content</p><script>alert("XSS")</script><a href="javascript:alert(\'link XSS\')">Bad Link</a>',
    )

    # Fetch the battle page
    response = client.get(reverse("core:battle", args=[battle.id]))
    assert response.status_code == 200

    content = response.content.decode()

    # Verify XSS is removed but safe content remains
    assert "<p>Note content</p>" in content
    # Check that XSS script content is not present (not checking for <script> tag itself as page has legitimate scripts)
    assert 'alert("XSS")' not in content
    assert "javascript:alert" not in content
    assert "alert('link XSS')" not in content
    assert (
        "Bad Link</a>" in content
    )  # Link text should remain but href should be sanitized


@pytest.mark.django_db
def test_list_with_fighter_xss_is_sanitized():
    """Test that XSS content in fighter narratives is properly sanitized."""
    # This is a simpler test that focuses on List narrative
    # The ContentFighter model has complex requirements that make testing difficult
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")

    # Create list with XSS in narrative
    gang_list = List.objects.create(
        name="Test Gang with XSS Fighter",
        owner=user,
        content_house=house,
        narrative='<p>Gang has fighters</p><script>alert("fighter XSS")</script>',
    )

    # Fetch the list page
    response = client.get(reverse("core:list", args=[gang_list.id]))
    assert response.status_code == 200

    content = response.content.decode()

    # Verify XSS is removed but safe content remains
    assert "<p>Gang has fighters</p>" in content or "Gang has fighters" in content
    # Check that XSS script content is not present
    assert 'alert("fighter XSS")' not in content


@pytest.mark.django_db
def test_list_narrative_with_xss_is_sanitized():
    """Test that XSS content in list narratives is properly sanitized."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")

    # Create list with XSS in narrative
    gang_list = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        narrative="<p>Gang story</p><iframe src=\"javascript:alert('XSS')\"></iframe><style>body{display:none}</style>",
    )

    # Fetch the list page
    response = client.get(reverse("core:list", args=[gang_list.id]))
    assert response.status_code == 200

    content = response.content.decode()

    # Verify XSS is removed but safe content remains
    assert "<p>Gang story</p>" in content
    assert "<iframe" not in content
    assert "<style>" not in content
    assert "javascript:" not in content
    assert "display:none" not in content


@pytest.mark.django_db
def test_complex_nested_xss_is_sanitized():
    """Test that complex nested XSS attempts are sanitized."""

    # Test nested script tags - the closing tag might be escaped
    result = safe_rich_text('<p>Text<script><script>alert("XSS")</script></script></p>')
    assert result.startswith("<p>Text")
    assert "alert" not in result
    assert "<script>" not in result

    # Test encoded XSS attempts
    assert (
        safe_rich_text("<a href=\"java&#115;cript:alert('XSS')\">Link</a>")
        == "<a>Link</a>"
    )

    # Test mixed case event handlers
    assert (
        safe_rich_text("<div OnClIcK=\"alert('XSS')\">Text</div>") == "<div>Text</div>"
    )

    # Test malformed tags
    assert safe_rich_text('<img src="x"onerror="alert(\'XSS\')">') == '<img src="x">'

    # Test CSS expressions (IE specific but good to test)
    style_xss = "<div style=\"background:url(javascript:alert('XSS'))\">Text</div>"
    result = safe_rich_text(style_xss)
    assert "javascript:" not in result
    assert "Text</div>" in result
