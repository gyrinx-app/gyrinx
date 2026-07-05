"""Tests for the navbar unread-count badge and its context processor."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.core.context_processors import notifications as notifications_cp
from gyrinx.core.models.notification import notify


@pytest.mark.django_db
def test_context_processor_anonymous_is_zero():
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    assert notifications_cp(request) == {"unread_notification_count": 0}


@pytest.mark.django_db
def test_context_processor_counts_active_unread(user):
    notify(recipient=user, subject="a")
    notify(recipient=user, subject="b")
    read = notify(recipient=user, subject="read")
    read.mark_read()
    archived = notify(recipient=user, subject="archived")
    archived.archive()

    request = RequestFactory().get("/")
    request.user = user
    assert notifications_cp(request) == {"unread_notification_count": 2}


@pytest.mark.django_db
def test_context_processor_scoped_to_user(user, make_user):
    other = make_user("other", "password")
    notify(recipient=other, subject="theirs")
    notify(recipient=user, subject="mine")

    request = RequestFactory().get("/")
    request.user = user
    assert notifications_cp(request)["unread_notification_count"] == 1


@pytest.mark.django_db
def test_badge_rendered_in_navbar_when_unread(client, user):
    notify(recipient=user, subject="ping")
    client.force_login(user)
    resp = client.get(reverse("core:index"))
    content = resp.content.decode()
    # The red count pill is shown.
    assert "badge rounded-pill text-bg-danger" in content
    assert 'href="/notifications/"' in content


@pytest.mark.django_db
def test_badge_absent_when_zero(client, user):
    client.force_login(user)
    resp = client.get(reverse("core:index"))
    content = resp.content.decode()
    # The inbox link is present, but not the red count pill.
    assert 'href="/notifications/"' in content
    assert "badge rounded-pill text-bg-danger" not in content


@pytest.mark.django_db
def test_badge_absent_for_anonymous(client, user):
    notify(recipient=user, subject="ping")
    resp = client.get(reverse("core:index"))
    content = resp.content.decode()
    assert "unread notifications" not in content


@pytest.mark.django_db
def test_navbar_tooltip_reflects_unread_state(client, user):
    client.force_login(user)
    zero = client.get(reverse("core:index")).content.decode()
    assert 'data-bs-title="No unread notifications"' in zero
    notify(recipient=user, subject="ping")
    unread = client.get(reverse("core:index")).content.decode()
    assert 'data-bs-title="You have unread notifications"' in unread
