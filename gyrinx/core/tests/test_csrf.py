"""Test custom CSRF failure handler."""

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_csrf_failure_redirects_with_message(client: Client):
    """Test that CSRF failure redirects back to form with an error message."""
    # Create a test URL (using new list as an example)
    form_url = reverse("core:lists-new")

    # Make a request without a CSRF token
    # First, get a valid session by loading the form
    response = client.get(form_url)
    assert response.status_code == 302  # Should redirect to login

    # Now test with an authenticated user
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="password")
    client.force_login(user)

    # Get the form page
    response = client.get(form_url)
    assert response.status_code == 200

    # Now post without CSRF token (simulating expired token)
    # We need to manually trigger the CSRF failure
    # Django's test client includes CSRF tokens by default, so we use a different approach

    # Save the current CSRF_FAILURE_VIEW setting
    from gyrinx.core.views import csrf_failure

    # Create a mock request
    from django.test import RequestFactory

    factory = RequestFactory()
    request = factory.post(form_url, data={"name": "Test List"})
    request.META["HTTP_REFERER"] = form_url
    request.session = client.session

    # Set up messages framework for the request
    setattr(request, "_messages", FallbackStorage(request))

    # Call the CSRF failure view directly
    response = csrf_failure(request, reason="CSRF token missing or incorrect")

    # Check that it redirects
    assert response.status_code == 302
    assert response.url == form_url

    # Check that the error message was added
    messages = list(get_messages(request))
    assert len(messages) == 1
    assert "Your session has expired" in str(messages[0])


@pytest.mark.django_db
def test_csrf_failure_redirects_to_home_without_referer(client: Client):
    """Test that CSRF failure redirects to home page when no referer is present."""
    from django.test import RequestFactory
    from gyrinx.core.views import csrf_failure

    factory = RequestFactory()
    request = factory.post("/some-url/", data={})
    # No referer header
    request.session = client.session

    # Set up messages framework for the request
    setattr(request, "_messages", FallbackStorage(request))

    response = csrf_failure(request, reason="CSRF token missing")

    # Should redirect to home
    assert response.status_code == 302
    # Use reverse to get the actual home URL
    from django.urls import reverse

    assert response.url == reverse("core:index")


@pytest.mark.django_db
def test_csrf_failure_view_is_csrf_exempt():
    """Test that the CSRF failure view itself is CSRF exempt."""
    from gyrinx.core.views import csrf_failure

    # Check that the view has been wrapped by csrf_exempt
    # The csrf_exempt decorator adds the attribute 'csrf_exempt' to the function
    assert getattr(csrf_failure, "csrf_exempt", False) is True


@pytest.mark.django_db
def test_csrf_failure_with_malicious_referer(client: Client):
    """Test that CSRF failure rejects malicious referer URLs."""
    from django.test import RequestFactory
    from gyrinx.core.views import csrf_failure
    from django.urls import reverse

    factory = RequestFactory()
    request = factory.post("/some-url/", data={})
    # Set a malicious referer from external domain
    request.META["HTTP_REFERER"] = "https://evil.com/steal-data"
    request.session = client.session

    # Set up messages framework for the request
    setattr(request, "_messages", FallbackStorage(request))

    response = csrf_failure(request, reason="CSRF token missing")

    # Should redirect to home, not the malicious URL
    assert response.status_code == 302
    assert response.url == reverse("core:index")


def test_csrf_failure_view_setting():
    """Test that CSRF_FAILURE_VIEW is properly configured in settings."""
    from django.conf import settings

    assert hasattr(settings, "CSRF_FAILURE_VIEW")
    assert settings.CSRF_FAILURE_VIEW == "gyrinx.core.views.csrf_failure"
