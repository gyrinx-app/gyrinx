"""Tests for the notification inbox views and actions."""

import pytest
from django.urls import reverse

from gyrinx.core.models.notification import (
    Notification,
    NotificationType,
    notify,
    notify_list_owner,
)


@pytest.mark.django_db
def test_inbox_requires_login(client):
    resp = client.get(reverse("core:notifications"))
    assert resp.status_code == 302
    assert "/accounts/login" in resp.url or "login" in resp.url


@pytest.mark.django_db
def test_inbox_shows_only_own_notifications(client, user, make_user):
    other = make_user("other", "password")
    notify(recipient=user, subject="mine")
    notify(recipient=other, subject="theirs")

    client.force_login(user)
    resp = client.get(reverse("core:notifications"))
    assert resp.status_code == 200
    subjects = [n.subject for n in resp.context["notifications"]]
    assert "mine" in subjects
    assert "theirs" not in subjects


@pytest.mark.django_db
def test_inbox_status_filter(client, user):
    unread = notify(recipient=user, subject="unread-one")
    read = notify(recipient=user, subject="read-one")
    read.mark_read()

    client.force_login(user)
    resp = client.get(reverse("core:notifications"), {"status": "unread"})
    subjects = [n.subject for n in resp.context["notifications"]]
    assert subjects == ["unread-one"]
    assert unread.subject in subjects


@pytest.mark.django_db
def test_inbox_type_filter(client, user, make_list):
    lst = make_list("Gang")
    notify_list_owner(lst, subject="list-note")  # type LIST
    notify(
        recipient=user,
        subject="general-note",
        notification_type=NotificationType.GENERAL,
    )

    client.force_login(user)
    resp = client.get(reverse("core:notifications"), {"type": "list"})
    subjects = [n.subject for n in resp.context["notifications"]]
    assert subjects == ["list-note"]


@pytest.mark.django_db
def test_inbox_search_filter(client, user):
    notify(recipient=user, subject="Cost recalculated", content="details here")
    notify(recipient=user, subject="Unrelated")

    client.force_login(user)
    resp = client.get(reverse("core:notifications"), {"q": "recalculated"})
    subjects = [n.subject for n in resp.context["notifications"]]
    assert subjects == ["Cost recalculated"]


@pytest.mark.django_db
def test_inbox_archived_bucket(client, user):
    notify(recipient=user, subject="active-one")
    arch = notify(recipient=user, subject="archived-one")
    arch.archive()

    client.force_login(user)
    resp = client.get(reverse("core:notifications"), {"bucket": "archived"})
    subjects = [n.subject for n in resp.context["notifications"]]
    assert subjects == ["archived-one"]


@pytest.mark.django_db
def test_inbox_pagination(client, user):
    for i in range(30):
        notify(recipient=user, subject=f"note-{i}")
    client.force_login(user)
    resp = client.get(reverse("core:notifications"))
    assert resp.context["is_paginated"] is True
    assert len(resp.context["notifications"]) == 25


@pytest.mark.django_db
def test_notification_read_action(client, user):
    n = notify(recipient=user, subject="x")
    client.force_login(user)
    resp = client.post(reverse("core:notification-read", args=[n.id]))
    assert resp.status_code == 302
    n.refresh_from_db()
    assert n.is_read is True


@pytest.mark.django_db
def test_notification_unread_action(client, user):
    n = notify(recipient=user, subject="x")
    n.mark_read()
    client.force_login(user)
    client.post(reverse("core:notification-unread", args=[n.id]))
    n.refresh_from_db()
    assert n.is_read is False


@pytest.mark.django_db
def test_notification_archive_and_delete_actions(client, user):
    n = notify(recipient=user, subject="x")
    client.force_login(user)
    client.post(reverse("core:notification-archive", args=[n.id]))
    n.refresh_from_db()
    assert n.archived is True

    client.post(reverse("core:notification-delete", args=[n.id]))
    n.refresh_from_db()
    assert n.deleted_at is not None


@pytest.mark.django_db
def test_action_on_other_users_notification_is_404(client, user, make_user):
    other = make_user("other", "password")
    n = notify(recipient=other, subject="theirs")
    client.force_login(user)
    resp = client.post(reverse("core:notification-read", args=[n.id]))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_action_rejects_get(client, user):
    n = notify(recipient=user, subject="x")
    client.force_login(user)
    resp = client.get(reverse("core:notification-read", args=[n.id]))
    assert resp.status_code == 405


@pytest.mark.django_db
def test_bulk_mark_all_read(client, user):
    for i in range(3):
        notify(recipient=user, subject=f"n-{i}")
    client.force_login(user)
    resp = client.post(
        reverse("core:notifications-bulk"),
        {"action": "mark_read", "all": "1", "bucket": "inbox", "status": "unread"},
    )
    assert resp.status_code == 302
    assert Notification.objects.filter(owner=user, is_read=False).count() == 0


@pytest.mark.django_db
def test_bulk_archive_selected(client, user):
    a = notify(recipient=user, subject="a")
    b = notify(recipient=user, subject="b")
    c = notify(recipient=user, subject="c")
    client.force_login(user)
    client.post(
        reverse("core:notifications-bulk"),
        {"action": "archive", "ids": [str(a.id), str(b.id)]},
    )
    a.refresh_from_db()
    b.refresh_from_db()
    c.refresh_from_db()
    assert a.archived is True
    assert b.archived is True
    assert c.archived is False


@pytest.mark.django_db
def test_bulk_scoped_to_owner(client, user, make_user):
    other = make_user("other", "password")
    theirs = notify(recipient=other, subject="theirs")
    client.force_login(user)
    # Attempt to delete another user's notification by id — must not affect it.
    client.post(
        reverse("core:notifications-bulk"),
        {"action": "delete", "ids": [str(theirs.id)]},
    )
    theirs.refresh_from_db()
    assert theirs.deleted_at is None


@pytest.mark.django_db
def test_dismiss_banner_marks_read(client, user, make_list):
    lst = make_list("Gang")
    n = notify_list_owner(lst, subject="banner", show_as_banner=True)
    client.force_login(user)
    resp = client.post(reverse("core:notification-dismiss-banner", args=[n.id]))
    assert resp.status_code == 302
    n.refresh_from_db()
    assert n.is_read is True


@pytest.mark.django_db
def test_inbox_renders_rich_text_content_sanitized(client, user):
    notify(
        recipient=user,
        subject="Rich",
        content="<p>Hello <strong>bold</strong></p><script>alert(1)</script>",
    )
    client.force_login(user)
    body = client.get(reverse("core:notifications")).content.decode()
    # Allowed formatting survives; dangerous tags are neutralised.
    assert "<strong>bold</strong>" in body
    assert "<script>alert(1)</script>" not in body
