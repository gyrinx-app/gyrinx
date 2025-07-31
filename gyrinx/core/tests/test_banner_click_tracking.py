import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gyrinx.core.models.events import Event, EventNoun, EventVerb
from gyrinx.core.models.site import Banner

User = get_user_model()


@pytest.mark.django_db
def test_track_banner_click_with_cta_url():
    """Test that clicking a banner with CTA URL logs event and redirects correctly."""
    # Create a live banner with CTA
    banner = Banner.objects.create(
        text="Test banner",
        cta_text="Learn More",
        cta_url="https://example.com",
        is_live=True,
    )

    client = Client()
    url = reverse("core:track-banner-click", kwargs={"id": banner.id})

    # Make the request
    response = client.get(url)

    # Check redirect
    assert response.status_code == 302
    assert response.url == "https://example.com"

    # Check that event was logged
    event = Event.objects.filter(
        noun=EventNoun.BANNER,
        verb=EventVerb.CLICK,
        object_id=banner.id,
    ).first()

    assert event is not None
    assert event.context["banner_text"] == "Test banner"
    assert event.context["cta_text"] == "Learn More"
    assert event.context["cta_url"] == "https://example.com"


@pytest.mark.django_db
def test_track_banner_click_without_cta_url():
    """Test that clicking a banner without CTA URL redirects to home."""
    # Create a live banner without CTA URL
    banner = Banner.objects.create(
        text="Test banner without CTA",
        is_live=True,
    )

    client = Client()
    url = reverse("core:track-banner-click", kwargs={"id": banner.id})

    # Make the request
    response = client.get(url)

    # Check redirect to home
    assert response.status_code == 302
    assert response.url == reverse("core:index")

    # Check that event was logged
    event = Event.objects.filter(
        noun=EventNoun.BANNER,
        verb=EventVerb.CLICK,
        object_id=banner.id,
    ).first()

    assert event is not None


@pytest.mark.django_db
def test_track_banner_click_non_live_banner():
    """Test that clicking a non-live banner returns 404."""
    # Create a non-live banner
    banner = Banner.objects.create(
        text="Non-live banner",
        cta_text="Learn More",
        cta_url="https://example.com",
        is_live=False,
    )

    client = Client()
    url = reverse("core:track-banner-click", kwargs={"id": banner.id})

    # Make the request
    response = client.get(url)

    # Should get 404
    assert response.status_code == 404

    # No event should be logged
    event_count = Event.objects.filter(
        noun=EventNoun.BANNER,
        verb=EventVerb.CLICK,
    ).count()

    assert event_count == 0


@pytest.mark.django_db
def test_track_banner_click_authenticated_user():
    """Test that banner clicks by authenticated users include user info."""
    # Create user
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create a live banner
    banner = Banner.objects.create(
        text="Test banner for auth user",
        cta_text="Click Me",
        cta_url="https://example.com",
        is_live=True,
    )

    client = Client()
    client.login(username="testuser", password="testpass")

    url = reverse("core:track-banner-click", kwargs={"id": banner.id})

    # Make the request
    response = client.get(url)

    # Check redirect
    assert response.status_code == 302
    assert response.url == "https://example.com"

    # Check that event was logged with user
    event = Event.objects.filter(
        noun=EventNoun.BANNER,
        verb=EventVerb.CLICK,
        object_id=banner.id,
    ).first()

    assert event is not None
    assert event.owner == user


@pytest.mark.django_db
def test_track_banner_click_invalid_banner_id():
    """Test that clicking with invalid banner ID redirects to home."""
    client = Client()

    # Use a non-existent banner ID
    url = reverse(
        "core:track-banner-click", kwargs={"id": "00000000-0000-0000-0000-000000000000"}
    )

    # Make the request
    response = client.get(url)

    # Should get 404
    assert response.status_code == 404
