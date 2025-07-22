import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.contrib.admin.sites import AdminSite
from allauth.account.models import EmailAddress
from allauth.account.admin import EmailAddressAdmin as AllauthEmailAddressAdmin

from gyrinx.core.admin.auth import EmailAddressAdmin, show_verification_links


@pytest.mark.django_db
def test_email_address_admin_is_registered():
    """Test that EmailAddress is registered in the admin."""
    assert EmailAddress in admin.site._registry
    assert isinstance(admin.site._registry[EmailAddress], EmailAddressAdmin)


@pytest.mark.django_db
def test_email_address_admin_inherits_from_allauth():
    """Test that our EmailAddressAdmin inherits from allauth's EmailAddressAdmin."""
    admin_instance = admin.site._registry[EmailAddress]
    assert isinstance(admin_instance, AllauthEmailAddressAdmin)
    # Check that the default allauth actions are preserved
    action_names = []
    for action in admin_instance.actions:
        if hasattr(action, "__name__"):
            action_names.append(action.__name__)
        elif isinstance(action, str):
            action_names.append(action)

    assert "make_verified" in action_names
    # Check that our custom action is added
    assert "show_verification_links" in action_names


@pytest.mark.django_db
def test_show_verification_links_action():
    """Test the show_verification_links admin action renders a table view."""
    # Create a user and email address
    user = User.objects.create_user(username="testuser", email="test@example.com")
    email_address = EmailAddress.objects.create(
        user=user, email="test@example.com", verified=False, primary=True
    )

    # Create admin and request
    site = AdminSite()
    admin_instance = EmailAddressAdmin(EmailAddress, site)
    factory = RequestFactory()
    request = factory.post("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    # Execute the action
    queryset = EmailAddress.objects.filter(pk=email_address.pk)
    response = show_verification_links(admin_instance, request, queryset)

    # Check that the response is an HttpResponse with the template
    assert response.status_code == 200
    assert b"Email Verification Links" in response.content
    assert b"test@example.com" in response.content
    assert b"Unverified" in response.content
    assert (
        b"/accounts/confirm-email/" in response.content
    )  # Part of the verification URL


@pytest.mark.django_db
def test_show_verification_links_skips_verified_emails():
    """Test that the action handles already verified emails."""
    # Create a user and verified email address
    user = User.objects.create_user(username="testuser", email="test@example.com")
    email_address = EmailAddress.objects.create(
        user=user, email="test@example.com", verified=True, primary=True
    )

    # Create admin and request
    site = AdminSite()
    admin_instance = EmailAddressAdmin(EmailAddress, site)
    factory = RequestFactory()
    request = factory.post("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    # Execute the action
    queryset = EmailAddress.objects.filter(pk=email_address.pk)
    response = show_verification_links(admin_instance, request, queryset)

    # Check that the response shows the email is already verified
    assert response.status_code == 200
    assert b"Email Verification Links" in response.content
    assert b"test@example.com" in response.content
    assert b"Already Verified" in response.content


@pytest.mark.django_db
def test_show_verification_links_csv_download():
    """Test the CSV download functionality."""
    # Create users and email addresses
    user1 = User.objects.create_user(username="testuser1", email="test1@example.com")
    user2 = User.objects.create_user(username="testuser2", email="test2@example.com")

    email1 = EmailAddress.objects.create(
        user=user1, email="test1@example.com", verified=False, primary=True
    )
    email2 = EmailAddress.objects.create(
        user=user2, email="test2@example.com", verified=True, primary=True
    )

    # Create admin and request
    site = AdminSite()
    admin_instance = EmailAddressAdmin(EmailAddress, site)
    factory = RequestFactory()
    request = factory.post("/admin/", {"download_csv": "1"})
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    # Execute the action
    queryset = EmailAddress.objects.filter(pk__in=[email1.pk, email2.pk])
    response = show_verification_links(admin_instance, request, queryset)

    # Check CSV response
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert (
        response["Content-Disposition"]
        == 'attachment; filename="verification_links.csv"'
    )

    # Check CSV content
    content = response.content.decode("utf-8")
    lines = content.strip().split("\n")
    assert len(lines) == 3  # Header + 2 data rows
    assert "Email Address,Status,Verification Link" in lines[0]
    assert "test1@example.com,Unverified,http" in content  # Should have a URL
    assert "test2@example.com,Already Verified," in content  # No URL for verified


@pytest.mark.django_db
def test_email_address_admin_prevents_manual_addition():
    """Test that manual addition of email addresses is disabled."""
    admin_instance = EmailAddressAdmin(EmailAddress, admin.site)
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    assert not admin_instance.has_add_permission(request)
