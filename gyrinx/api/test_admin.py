import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory

from gyrinx.api.admin import WebhookRequestAdmin
from gyrinx.api.models import WebhookRequest


@pytest.fixture
def webhook_admin():
    return WebhookRequestAdmin(WebhookRequest, AdminSite())


@pytest.fixture
def admin_request():
    factory = RequestFactory()
    request = factory.get("/admin/")
    return request


@pytest.mark.django_db
def test_webhook_admin_search_by_email(webhook_admin, admin_request):
    """Test that WebhookRequestAdmin can search by email in the JSON payload."""
    admin_request.user = User.objects.create_superuser(
        "admin",
        "admin@test.com",
        "password",  # nosec B106
    )

    wh = WebhookRequest.objects.create(
        source="patreon",
        event="members:pledge:create",
        payload={
            "data": {
                "attributes": {
                    "email": "patron@example.com",
                    "full_name": "Jane Patron",
                }
            }
        },
    )
    # Unrelated webhook
    WebhookRequest.objects.create(
        source="patreon",
        event="members:pledge:create",
        payload={
            "data": {
                "attributes": {
                    "email": "other@example.com",
                    "full_name": "Other User",
                }
            }
        },
    )

    qs = WebhookRequest.objects.all()
    result_qs, _ = webhook_admin.get_search_results(admin_request, qs, "patron@example")
    assert wh in result_qs
    assert result_qs.count() == 1


@pytest.mark.django_db
def test_webhook_admin_search_by_name(webhook_admin, admin_request):
    """Test that WebhookRequestAdmin can search by full_name in the JSON payload."""
    admin_request.user = User.objects.create_superuser(
        "admin",
        "admin@test.com",
        "password",  # nosec B106
    )

    wh = WebhookRequest.objects.create(
        source="patreon",
        event="members:pledge:create",
        payload={
            "data": {
                "attributes": {
                    "email": "patron@example.com",
                    "full_name": "Jane Patron",
                }
            }
        },
    )

    qs = WebhookRequest.objects.all()
    result_qs, _ = webhook_admin.get_search_results(admin_request, qs, "Jane Patron")
    assert wh in result_qs


@pytest.mark.django_db
def test_webhook_admin_search_still_works_for_source_and_event(
    webhook_admin, admin_request
):
    """Test that the default source/event search still works."""
    admin_request.user = User.objects.create_superuser(
        "admin",
        "admin@test.com",
        "password",  # nosec B106
    )

    wh = WebhookRequest.objects.create(
        source="patreon",
        event="members:pledge:create",
        payload={"data": {"attributes": {}}},
    )

    qs = WebhookRequest.objects.all()
    result_qs, _ = webhook_admin.get_search_results(admin_request, qs, "patreon")
    assert wh in result_qs


@pytest.mark.django_db
def test_webhook_admin_list_display_includes_email_and_name(webhook_admin):
    """Test that list_display includes email and name columns."""
    display_names = []
    for item in webhook_admin.list_display:
        if callable(item):
            display_names.append(getattr(item, "short_description", str(item)))
        else:
            display_names.append(item)
    assert "Email" in display_names
    assert "Name" in display_names
