import json

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory

from gyrinx.core.adapter import CustomAccountAdapter

User = get_user_model()


@pytest.mark.django_db
def test_adapter_adds_email_headers(settings):
    """Test that the adapter adds EMAIL_EXTRA_HEADERS to emails."""
    adapter = CustomAccountAdapter()

    # Create a test user
    user = User.objects.create_user(username="testuser", email="test@example.com")

    # Set up test headers
    test_headers = {
        "X-Auto-Response-Suppress": "OOF, DR, RN, NRN, AutoReply",
        "List-Unsubscribe": "<mailto:unsubscribe@gyrinx.app>",
        "X-Custom-Header": "test-value",
    }

    settings.EMAIL_EXTRA_HEADERS = json.dumps(test_headers)
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    # Clear mail outbox
    mail.outbox = []

    # Create a mock request
    request = RequestFactory().get("/")

    # Send an email using the adapter
    adapter.send_mail(
        template_prefix="account/email/email_confirmation",
        email="test@example.com",
        context={
            "user": user,
            "activate_url": "http://example.com/activate",
            "request": request,
            "current_site": {"domain": "example.com", "name": "Example"},
        },
    )

    # Check that email was sent
    assert len(mail.outbox) == 1

    # Check that headers were added
    message = mail.outbox[0]
    assert hasattr(message, "extra_headers")
    for key, value in test_headers.items():
        assert message.extra_headers.get(key) == value, (
            f"Header {key} not found or incorrect"
        )


@pytest.mark.django_db
def test_adapter_handles_no_extra_headers_setting(settings):
    """Test that the adapter works when EMAIL_EXTRA_HEADERS is not set."""
    adapter = CustomAccountAdapter()

    # Create a test user
    user = User.objects.create_user(username="testuser", email="test@example.com")

    # Remove the setting if it exists
    if hasattr(settings, "EMAIL_EXTRA_HEADERS"):
        delattr(settings, "EMAIL_EXTRA_HEADERS")

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    # Clear mail outbox
    mail.outbox = []

    # Create a mock request
    request = RequestFactory().get("/")

    # Should not raise an exception
    adapter.send_mail(
        template_prefix="account/email/email_confirmation",
        email="test@example.com",
        context={
            "user": user,
            "activate_url": "http://example.com/activate",
            "request": request,
            "current_site": {"domain": "example.com", "name": "Example"},
        },
    )

    # Email should be sent
    assert len(mail.outbox) == 1
