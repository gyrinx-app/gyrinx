"""
Tests for event logging via Django signals.

These tests verify that authentication and user events from
third-party packages like allauth are properly logged.
"""

import pytest
from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed, user_logged_in, user_signed_up
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_out
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from gyrinx.core.models.events import Event, EventField, EventNoun, EventVerb

User = get_user_model()


@pytest.mark.django_db
def test_user_login_signal_logs_event():
    """Test that user login via allauth signals creates an event."""
    user = User.objects.create_user(username="testuser", password="testpass123")

    # Create a mock request
    factory = RequestFactory()
    request = factory.get("/")
    # Create a proper session object
    request.session = SessionStore()
    request.session.save()  # This creates a session_key
    request.META["REMOTE_ADDR"] = "192.168.1.1"
    # Add user to request to simulate authenticated request
    request.user = user

    # Clear any existing events
    Event.objects.all().delete()

    # Send the signal
    user_logged_in.send(sender=User, request=request, user=user)

    # Check that an event was logged
    assert Event.objects.count() == 1
    event = Event.objects.first()
    assert event.owner == user
    assert event.noun == EventNoun.USER
    assert event.verb == EventVerb.LOGIN
    assert event.context.get("login_method") == "email"
    assert event.ip_address == "192.168.1.1"


@pytest.mark.django_db
def test_user_logout_signal_logs_event():
    """Test that user logout creates an event."""
    user = User.objects.create_user(username="testuser", password="testpass123")

    # Create a mock request
    factory = RequestFactory()
    request = factory.get("/")
    # Create a proper session object
    request.session = SessionStore()
    request.session.save()  # This creates a session_key
    request.META["REMOTE_ADDR"] = "192.168.1.2"
    # Add user to request to simulate authenticated request
    request.user = user

    # Clear any existing events
    Event.objects.all().delete()

    # Send the signal
    user_logged_out.send(sender=User, request=request, user=user)

    # Check that an event was logged
    assert Event.objects.count() == 1
    event = Event.objects.first()
    assert event.owner == user
    assert event.noun == EventNoun.USER
    assert event.verb == EventVerb.LOGOUT
    assert event.ip_address == "192.168.1.2"


@pytest.mark.django_db
def test_user_signup_signal_logs_event():
    """Test that user signup via allauth creates an event."""
    user = User.objects.create_user(username="newuser")

    # Create a mock request
    factory = RequestFactory()
    request = factory.get("/")
    # Create a proper session object
    request.session = SessionStore()
    request.session.save()  # This creates a session_key
    request.META["REMOTE_ADDR"] = "192.168.1.3"
    # Add user to request to simulate authenticated request
    request.user = user

    # Clear any existing events
    Event.objects.all().delete()

    # Send the signal
    user_signed_up.send(sender=User, request=request, user=user)

    # Check that an event was logged
    assert Event.objects.count() == 1
    event = Event.objects.first()
    assert event.owner == user
    assert event.noun == EventNoun.USER
    assert event.verb == EventVerb.SIGNUP
    assert event.context["sociallogin"] is False
    assert event.ip_address == "192.168.1.3"


@pytest.mark.django_db
def test_email_confirmed_signal_logs_event():
    """Test that email confirmation creates an event."""
    user = User.objects.create_user(username="testuser", email="test@example.com")
    email_address = EmailAddress.objects.create(
        user=user,
        email="test@example.com",
        primary=True,
        verified=True,
    )

    # Create a mock request
    factory = RequestFactory()
    request = factory.get("/")
    # Create a proper session object
    request.session = SessionStore()
    request.session.save()  # This creates a session_key
    request.META["REMOTE_ADDR"] = "192.168.1.4"
    # Add user to request to simulate authenticated request
    request.user = user

    # Clear any existing events
    Event.objects.all().delete()

    # Send the signal
    email_confirmed.send(
        sender=EmailAddress,
        request=request,
        email_address=email_address,
    )

    # Check that an event was logged
    assert Event.objects.count() == 1
    event = Event.objects.first()
    assert event.owner == user
    assert event.noun == EventNoun.USER
    assert event.verb == EventVerb.UPDATE
    assert event.field == EventField.EMAIL
    assert event.context["email"] == "test@example.com"
    assert event.context["primary"] is True
    assert event.ip_address == "192.168.1.4"
