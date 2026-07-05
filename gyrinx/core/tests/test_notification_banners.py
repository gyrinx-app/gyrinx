"""Tests for the in-page notification banner surface on lists and campaigns."""

import pytest
from django.urls import reverse

from gyrinx.core.models.notification import (
    notify_campaign_arbitrator,
    notify_list_owner,
)


def _dismiss_marker(notification):
    return reverse("core:notification-dismiss-banner", args=[notification.id])


@pytest.mark.django_db
def test_banner_shows_on_list_for_owner(client, user, make_list):
    lst = make_list("Gang")
    n = notify_list_owner(lst, subject="Cost recalculated", show_as_banner=True)

    client.force_login(user)
    resp = client.get(reverse("core:list", args=[lst.id]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Cost recalculated" in content
    assert _dismiss_marker(n) in content


@pytest.mark.django_db
def test_banner_not_shown_when_flag_off(client, user, make_list):
    lst = make_list("Gang")
    notify_list_owner(lst, subject="No banner", show_as_banner=False)

    client.force_login(user)
    resp = client.get(reverse("core:list", args=[lst.id]))
    assert list(resp.context["notification_banners"]) == []


@pytest.mark.django_db
def test_banner_not_shown_to_other_user(client, user, make_user, make_list):
    lst = make_list("Gang")
    n = notify_list_owner(lst, subject="Owner only", show_as_banner=True)

    other = make_user("other", "password")
    client.force_login(other)
    resp = client.get(reverse("core:list", args=[lst.id]))
    assert _dismiss_marker(n) not in resp.content.decode()


@pytest.mark.django_db
def test_banner_gone_after_read(client, user, make_list):
    lst = make_list("Gang")
    n = notify_list_owner(lst, subject="Once", show_as_banner=True)
    n.mark_read()

    client.force_login(user)
    resp = client.get(reverse("core:list", args=[lst.id]))
    assert list(resp.context["notification_banners"]) == []


@pytest.mark.django_db
def test_banner_shows_on_campaign_for_arbitrator(client, user, campaign):
    n = notify_campaign_arbitrator(
        campaign, subject="A list in your campaign changed", show_as_banner=True
    )
    client.force_login(user)  # campaign fixture is owned by `user`
    resp = client.get(reverse("core:campaign", args=[campaign.id]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "A list in your campaign changed" in content
    assert _dismiss_marker(n) in content


@pytest.mark.django_db
def test_dismiss_banner_removes_it(client, user, make_list):
    lst = make_list("Gang")
    n = notify_list_owner(lst, subject="Dismiss me", show_as_banner=True)

    client.force_login(user)
    resp = client.post(reverse("core:notification-dismiss-banner", args=[n.id]))
    assert resp.status_code == 302
    n.refresh_from_db()
    assert n.is_read is True

    resp = client.get(reverse("core:list", args=[lst.id]))
    assert list(resp.context["notification_banners"]) == []
