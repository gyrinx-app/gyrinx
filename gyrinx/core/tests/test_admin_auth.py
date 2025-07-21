"""Tests for auth admin functionality."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.admin.sites import site
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.core.admin.auth import EmailAddressAdmin, send_verification_email


@pytest.mark.django_db
def test_email_address_admin_registered():
    """Test that EmailAddress model is registered in admin."""
    assert EmailAddress in site._registry
    assert isinstance(site._registry[EmailAddress], EmailAddressAdmin)


@pytest.mark.django_db
def test_email_address_admin_has_send_verification_action():
    """Test that EmailAddressAdmin has send_verification_email action."""
    admin = site._registry[EmailAddress]
    assert send_verification_email in admin.actions


@pytest.mark.django_db
def test_send_verification_email_action(admin_user, client):
    """Test sending verification emails through admin action."""
    # Create a user with an unverified email
    user = User.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )
    email_address = EmailAddress.objects.create(
        user=user, email="test@example.com", verified=False, primary=True
    )

    # Login as admin
    client.force_login(admin_user)

    # Get the changelist URL
    url = reverse("admin:account_emailaddress_changelist")

    # Select the email address and apply the action
    data = {
        "action": "send_verification_email",
        "_selected_action": [str(email_address.pk)],
    }

    response = client.post(url, data, follow=True)

    # Check that we got a success message
    messages = list(get_messages(response.wsgi_request))
    assert any("Sent verification email to 1 address(es)." in str(m) for m in messages)


@pytest.mark.django_db
def test_send_verification_email_skips_verified_emails(admin_user, client):
    """Test that the action skips already verified emails."""
    # Create a user with a verified email
    user = User.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )
    email_address = EmailAddress.objects.create(
        user=user, email="test@example.com", verified=True, primary=True
    )

    # Login as admin
    client.force_login(admin_user)

    # Get the changelist URL
    url = reverse("admin:account_emailaddress_changelist")

    # Select the email address and apply the action
    data = {
        "action": "send_verification_email",
        "_selected_action": [str(email_address.pk)],
    }

    response = client.post(url, data, follow=True)

    # Check that no emails were sent (since it's already verified)
    messages = list(get_messages(response.wsgi_request))
    # The action should complete but not send any emails to verified addresses
    assert not any("Sent verification email" in str(m) for m in messages)


@pytest.mark.django_db
def test_email_address_admin_cannot_add():
    """Test that EmailAddressAdmin prevents manual addition."""
    admin = site._registry[EmailAddress]
    rf = RequestFactory()
    request = rf.get("/admin/")
    assert not admin.has_add_permission(request)
