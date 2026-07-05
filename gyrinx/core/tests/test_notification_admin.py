"""Tests for the notification admin and broadcast view."""

import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.core.admin.notification import NotificationAdmin
from gyrinx.core.models.notification import Notification


@pytest.fixture
def superuser(make_user):
    u = make_user("admin", "password")
    u.is_staff = True
    u.is_superuser = True
    u.save()
    return u


@pytest.mark.django_db
def test_save_model_defaults_owner_to_request_user(superuser):
    ma = NotificationAdmin(Notification, admin.site)
    request = RequestFactory().post("/")
    request.user = superuser
    obj = Notification(subject="Hi")
    ma.save_model(request, obj, form=None, change=False)
    obj.refresh_from_db()
    assert obj.owner == superuser


@pytest.mark.django_db
def test_broadcast_to_all_active_users(client, superuser, make_user):
    make_user("a", "password")
    make_user("b", "password")

    client.force_login(superuser)
    resp = client.post(
        reverse("admin:core_notification_broadcast"),
        {
            "subject": "Everyone read this",
            "content": "",
            "notification_type": "general",
            "audience": "all_active",
        },
    )
    assert resp.status_code == 302
    # admin + a + b = 3 active users, each gets one notification.
    assert Notification.objects.count() == 3
    assert Notification.objects.filter(subject="Everyone read this").count() == 3
    # send_as_system was not submitted (unchecked) → attributed to the acting admin.
    assert Notification.objects.first().sender == superuser


@pytest.mark.django_db
def test_broadcast_as_system_has_no_sender(client, superuser, make_user):
    make_user("a", "password")

    client.force_login(superuser)
    resp = client.post(
        reverse("admin:core_notification_broadcast"),
        {
            "subject": "From Gyrinx",
            "notification_type": "general",
            "audience": "all_active",
            "send_as_system": "on",
        },
    )
    assert resp.status_code == 302
    n = Notification.objects.filter(subject="From Gyrinx").first()
    assert n is not None
    assert n.sender is None
    assert n.is_system is True


@pytest.mark.django_db
def test_broadcast_to_campaign_participants(
    client, superuser, make_user, make_campaign, make_list
):
    owner = make_user("camp-owner", "password")
    list_owner = make_user("list-owner", "password")
    camp = make_campaign("Camp", owner=owner)
    lst = make_list("Gang", owner=list_owner)
    camp.lists.add(lst)

    client.force_login(superuser)
    resp = client.post(
        reverse("admin:core_notification_broadcast"),
        {
            "subject": "Campaign notice",
            "notification_type": "campaign",
            "audience": "campaign",
            "campaign": str(camp.id),
        },
    )
    assert resp.status_code == 302
    recipients = set(Notification.objects.values_list("owner__username", flat=True))
    assert recipients == {"camp-owner", "list-owner"}


@pytest.mark.django_db
def test_broadcast_to_users_with_a_list(client, superuser, make_user, make_list):
    list_owner = make_user("has-list", "password")
    make_user("no-list", "password")
    make_list("Their Gang", owner=list_owner)

    client.force_login(superuser)
    resp = client.post(
        reverse("admin:core_notification_broadcast"),
        {
            "subject": "For list owners",
            "notification_type": "general",
            "audience": "with_list",
        },
    )
    assert resp.status_code == 302
    recipients = set(Notification.objects.values_list("owner__username", flat=True))
    assert "has-list" in recipients
    assert "no-list" not in recipients


@pytest.mark.django_db
def test_broadcast_campaign_audience_requires_campaign(client, superuser):
    client.force_login(superuser)
    resp = client.post(
        reverse("admin:core_notification_broadcast"),
        {
            "subject": "Oops",
            "notification_type": "campaign",
            "audience": "campaign",
        },
    )
    # Re-renders the form with an error (no redirect), nothing created.
    assert resp.status_code == 200
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_broadcast_requires_superuser(client, make_user):
    staff = make_user("staff", "password")
    staff.is_staff = True
    staff.save()
    client.force_login(staff)
    resp = client.get(reverse("admin:core_notification_broadcast"))
    assert resp.status_code == 403
