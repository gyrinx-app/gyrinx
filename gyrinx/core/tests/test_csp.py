import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.skip
def test_csp_headers_present():
    """Test that CSP headers are present on responses."""
    client = Client()
    response = client.get(reverse("core:index"))

    # Check that CSP header is present
    assert response.has_header("Content-Security-Policy"), (
        "CSP header not found in response"
    )

    # Get the CSP header value
    csp_header = response["Content-Security-Policy"]

    # Verify key directives are present
    assert "default-src 'self'" in csp_header
    assert "script-src" in csp_header
    assert "style-src" in csp_header
    assert "img-src" in csp_header
    assert "font-src" in csp_header


@pytest.mark.django_db
@pytest.mark.skip
def test_csp_allows_tinymce(user):
    """Test that CSP allows TinyMCE to function."""
    client = Client()
    client.force_login(user)

    # Test campaign creation page which uses TinyMCE
    response = client.get(reverse("core:campaigns-new"))

    assert response.status_code == 200
    csp_header = response["Content-Security-Policy"]

    # Verify unsafe-inline is allowed for TinyMCE
    assert "'unsafe-inline'" in csp_header

    # Verify self is allowed for scripts
    assert "script-src 'self'" in csp_header

    # Verify data URLs are allowed for images (TinyMCE uses these)
    assert "img-src 'self' data:" in csp_header


@pytest.mark.django_db
@pytest.mark.skip
def test_csp_allows_external_resources():
    """Test that CSP allows required external resources."""
    client = Client()
    response = client.get(reverse("core:index"))

    csp_header = response["Content-Security-Policy"]

    # Check Bootstrap CDN is allowed
    assert "https://cdn.jsdelivr.net" in csp_header

    # Check Google Analytics/Tag Manager is allowed
    assert "https://www.googletagmanager.com" in csp_header
    assert "https://www.google-analytics.com" in csp_header

    # Check CookieYes is allowed
    assert "https://cdn-cookieyes.com" in csp_header


@pytest.mark.django_db
@pytest.mark.skip
def test_csp_security_directives():
    """Test that important security directives are set."""
    client = Client()
    response = client.get(reverse("core:index"))

    csp_header = response["Content-Security-Policy"]

    # Frame ancestors should allow embedding
    assert "frame-ancestors *" in csp_header

    # Object source should be restricted
    assert "object-src 'none'" in csp_header

    # Form actions should be restricted to self
    assert "form-action 'self'" in csp_header

    # Base URI should be restricted to self
    assert "base-uri 'self'" in csp_header

    # Upgrade insecure requests should be enabled
    assert "upgrade-insecure-requests" in csp_header

    # Block all mixed content should be enabled
    assert "block-all-mixed-content" in csp_header


@pytest.mark.django_db
@pytest.mark.skip
def test_embed_view_allows_iframe():
    """Test that embed views can be loaded in iframes."""
    from gyrinx.content.models import ContentFighter, ContentHouse
    from gyrinx.core.models import List, ListFighter

    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category="JUVE",  # Use a valid category
        house=house,
    )
    lst = List.objects.create(name="Test List", owner=user, content_house=house)
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        list=lst,
        content_fighter=content_fighter,
        owner=user,
    )

    client = Client()
    response = client.get(reverse("core:list-fighter-embed", args=[lst.id, fighter.id]))

    assert response.status_code == 200

    # Check CSP allows embedding
    csp_header = response["Content-Security-Policy"]
    assert "frame-ancestors *" in csp_header

    # Check iframe-resizer script is in the content
    assert "iframe-resizer" in response.content.decode()
