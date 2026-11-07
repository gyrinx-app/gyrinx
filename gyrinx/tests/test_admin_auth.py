import pytest
from allauth.account.admin import EmailAddressAdmin as AllauthEmailAddressAdmin
from allauth.account.models import EmailAddress
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory

from gyrinx.accounts.admin import (
    EmailAddressAdmin,
    UserProfileAdmin,
    show_verification_links,
)
from gyrinx.accounts.models import UserProfile

pytestmark = pytest.mark.core


@pytest.mark.django_db
def test_email_address_admin_is_registered():

    assert EmailAddress in admin.site._registry
    assert isinstance(admin.site._registry[EmailAddress], EmailAddressAdmin)


@pytest.mark.django_db
def test_email_address_admin_inherits_from_allauth():

    admin_instance = admin.site._registry[EmailAddress]
    assert isinstance(admin_instance, AllauthEmailAddressAdmin)
    action_names = []
    for action in admin_instance.actions:
        if hasattr(action, "__name__"):
            action_names.append(action.__name__)
        elif isinstance(action, str):
            action_names.append(action)

    assert "make_verified" in action_names
    assert "show_verification_links" in action_names


@pytest.mark.django_db
def test_show_verification_links_action():

    user = User.objects.create_user(username="testuser", email="test@example.com")
    email_address = EmailAddress.objects.create(
        user=user, email="test@example.com", verified=False, primary=True
    )

    site = AdminSite()
    admin_instance = EmailAddressAdmin(EmailAddress, site)
    factory = RequestFactory()
    request = factory.post("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    queryset = EmailAddress.objects.filter(pk=email_address.pk)
    response = show_verification_links(admin_instance, request, queryset)

    assert response.status_code == 200
    assert b"Email Verification Links" in response.content
    assert b"test@example.com" in response.content
    assert b"Unverified" in response.content
    assert (
        b"/accounts/confirm-email/" in response.content
    )  # Part of the verification URL


@pytest.mark.django_db
def test_show_verification_links_skips_verified_emails():

    user = User.objects.create_user(username="testuser", email="test@example.com")
    email_address = EmailAddress.objects.create(
        user=user, email="test@example.com", verified=True, primary=True
    )

    site = AdminSite()
    admin_instance = EmailAddressAdmin(EmailAddress, site)
    factory = RequestFactory()
    request = factory.post("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    queryset = EmailAddress.objects.filter(pk=email_address.pk)
    response = show_verification_links(admin_instance, request, queryset)

    assert response.status_code == 200
    assert b"Email Verification Links" in response.content
    assert b"test@example.com" in response.content
    assert b"Already Verified" in response.content


@pytest.mark.django_db
def test_show_verification_links_csv_download():

    user1 = User.objects.create_user(username="testuser1", email="test1@example.com")
    user2 = User.objects.create_user(username="testuser2", email="test2@example.com")

    email1 = EmailAddress.objects.create(
        user=user1, email="test1@example.com", verified=False, primary=True
    )
    email2 = EmailAddress.objects.create(
        user=user2, email="test2@example.com", verified=True, primary=True
    )

    site = AdminSite()
    admin_instance = EmailAddressAdmin(EmailAddress, site)
    factory = RequestFactory()
    request = factory.post("/admin/", {"download_csv": "1"})
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    queryset = EmailAddress.objects.filter(pk__in=[email1.pk, email2.pk])
    response = show_verification_links(admin_instance, request, queryset)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert (
        response["Content-Disposition"]
        == 'attachment; filename="verification_links.csv"'
    )

    content = response.content.decode("utf-8")
    lines = content.strip().split("\n")
    assert len(lines) == 3  # Header + 2 data rows
    assert "Email Address,Status,Verification Link" in lines[0]
    assert "test1@example.com,Unverified,http" in content  # Should have a URL
    assert "test2@example.com,Already Verified," in content  # No URL for verified


@pytest.mark.django_db
def test_email_address_admin_prevents_manual_addition():

    admin_instance = EmailAddressAdmin(EmailAddress, admin.site)
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    assert not admin_instance.has_add_permission(request)


@pytest.mark.django_db
def test_user_profile_admin_search_by_patreon_email():

    user = User.objects.create_user(
        username="patron1", email="django@example.com", password="password"
    )
    profile = UserProfile.objects.create(
        user=user,
        patreon_email="patron@patreon.example.com",
        patreon_member_id="abc123",
    )

    site = AdminSite()
    admin_instance = UserProfileAdmin(UserProfile, site)
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    qs = UserProfile.objects.all()
    result_qs, use_distinct = admin_instance.get_search_results(
        request, qs, "patron@patreon"
    )
    assert profile in result_qs

    result_qs, use_distinct = admin_instance.get_search_results(request, qs, "abc123")
    assert profile in result_qs

    result_qs, use_distinct = admin_instance.get_search_results(
        request, qs, "django@example"
    )
    assert profile in result_qs


@pytest.mark.django_db
def test_user_profile_admin_has_patreon_tier_filter():

    admin_instance = UserProfileAdmin(UserProfile, AdminSite())
    assert "patreon_tier" in admin_instance.list_filter


@pytest.mark.django_db
def test_user_profile_admin_displays_patreon_email():

    admin_instance = UserProfileAdmin(UserProfile, AdminSite())
    assert "patreon_email" in admin_instance.list_display
