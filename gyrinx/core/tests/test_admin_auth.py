import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from allauth.account.models import EmailAddress

from gyrinx.core.admin.auth import EmailAddressAdmin, show_verification_links


@pytest.mark.django_db
def test_email_address_admin_is_registered():
    """Test that EmailAddress is registered in the admin."""
    assert EmailAddress in admin.site._registry
    assert isinstance(admin.site._registry[EmailAddress], EmailAddressAdmin)


@pytest.mark.django_db
def test_show_verification_links_action():
    """Test the show_verification_links admin action."""
    # Create a user and email address
    user = User.objects.create_user(username="testuser", email="test@example.com")
    email_address = EmailAddress.objects.create(
        user=user, email="test@example.com", verified=False, primary=True
    )

    # Create admin and request
    admin_instance = EmailAddressAdmin(EmailAddress, admin.site)
    factory = RequestFactory()
    request = factory.post("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    # Set up messages framework
    setattr(request, 'session', 'session')
    messages_storage = FallbackStorage(request)
    setattr(request, '_messages', messages_storage)

    # Execute the action
    queryset = EmailAddress.objects.filter(pk=email_address.pk)
    show_verification_links(admin_instance, request, queryset)

    # Check that a success message with the verification link was added
    messages = list(get_messages(request))
    assert len(messages) == 1
    assert "Verification link for test@example.com:" in str(messages[0])
    assert "/accounts/confirm-email/" in str(
        messages[0]
    )  # Part of the verification URL


@pytest.mark.django_db
def test_show_verification_links_skips_verified_emails():
    """Test that the action skips already verified emails."""
    # Create a user and verified email address
    user = User.objects.create_user(username="testuser", email="test@example.com")
    email_address = EmailAddress.objects.create(
        user=user, email="test@example.com", verified=True, primary=True
    )

    # Create admin and request
    admin_instance = EmailAddressAdmin(EmailAddress, admin.site)
    factory = RequestFactory()
    request = factory.post("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    # Set up messages framework
    setattr(request, 'session', 'session')
    messages_storage = FallbackStorage(request)
    setattr(request, '_messages', messages_storage)

    # Execute the action
    queryset = EmailAddress.objects.filter(pk=email_address.pk)
    show_verification_links(admin_instance, request, queryset)

    # Check that an info message was added saying email is already verified
    messages = list(get_messages(request))
    assert len(messages) == 2  # One info message per email, plus summary
    assert "test@example.com is already verified" in str(messages[0])
    assert "All selected email addresses are already verified" in str(messages[1])


@pytest.mark.django_db
def test_email_address_admin_prevents_manual_addition():
    """Test that manual addition of email addresses is disabled."""
    admin_instance = EmailAddressAdmin(EmailAddress, admin.site)
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    assert not admin_instance.has_add_permission(request)
