"""Tests for the Notification model and creation service."""

import pytest

from n23.core.models.list import List
from n23.core.models.notification import (
    Notification,
    NotificationType,
    notify,
    notify_campaign_arbitrator,
    notify_list_changed,
    notify_list_owner,
    notify_many,
)


@pytest.mark.django_db
def test_notify_creates_row_with_owner_as_recipient(user, make_user):
    sender = make_user("sender", "password")
    n = notify(
        recipient=user,
        subject="Hello",
        content="World",
        sender=sender,
        notification_type=NotificationType.GENERAL,
    )
    assert n is not None
    assert n.owner == user
    assert n.recipient == user
    assert n.sender == sender
    assert n.subject == "Hello"
    assert n.content == "World"
    assert n.notification_type == NotificationType.GENERAL
    assert n.is_read is False
    assert n.is_system is False


@pytest.mark.django_db
def test_notify_without_sender_is_system(user):
    n = notify(recipient=user, subject="Maintenance done")
    assert n is not None
    assert n.sender is None
    assert n.is_system is True
    assert n.sender_label == "Gyrinx"
    assert n.notification_type == NotificationType.SYSTEM  # default


@pytest.mark.django_db
def test_sender_label_uses_username_when_present(user, make_user):
    sender = make_user("alice", "password")
    n = notify(recipient=user, subject="Hi", sender=sender)
    assert n.sender_label == "alice"


@pytest.mark.django_db
def test_notify_with_no_recipient_returns_none():
    assert notify(recipient=None, subject="Nobody") is None
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_notify_never_raises(user, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(Notification.objects, "create_with_user", boom)
    # Must not propagate.
    assert notify(recipient=user, subject="X") is None


@pytest.mark.django_db
def test_notify_list_owner_sets_related_list(make_list):
    lst = make_list("My Gang")
    n = notify_list_owner(lst, subject="Your gang changed")
    assert n is not None
    assert n.owner == lst.owner
    assert n.related_list == lst
    assert n.notification_type == NotificationType.LIST


@pytest.mark.django_db
def test_notify_list_owner_no_owner_is_noop(make_list):
    lst = make_list("Ownerless")
    List.objects.filter(pk=lst.pk).update(owner=None)
    lst.refresh_from_db()
    assert notify_list_owner(lst, subject="X") is None
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_notify_campaign_arbitrator_sets_recipient_and_campaign(campaign):
    n = notify_campaign_arbitrator(campaign, subject="A list changed")
    assert n is not None
    assert n.owner == campaign.owner
    assert n.related_campaign == campaign
    assert n.notification_type == NotificationType.CAMPAIGN


@pytest.mark.django_db
def test_notify_list_changed_notifies_owner_and_arbitrator(
    user, make_user, make_campaign, make_list
):
    arbitrator = make_user("arbitrator", "password")
    camp = make_campaign("Camp", owner=arbitrator)
    lst = make_list("Gang", status=List.CAMPAIGN_MODE, campaign=camp)
    camp.lists.add(lst)

    notify_list_changed(lst, subject="Cost recalculated")

    # Owner (user) gets one, arbitrator gets one.
    assert Notification.objects.filter(owner=user).count() == 1
    assert Notification.objects.filter(owner=arbitrator).count() == 1
    arb_note = Notification.objects.get(owner=arbitrator)
    assert arb_note.related_campaign == camp
    assert arb_note.related_list == lst


@pytest.mark.django_db
def test_notify_list_changed_does_not_double_notify_when_owner_is_arbitrator(
    user, make_campaign, make_list
):
    # Campaign owned by the same user who owns the list.
    camp = make_campaign("Camp", owner=user)
    lst = make_list("Gang", status=List.CAMPAIGN_MODE, campaign=camp)
    camp.lists.add(lst)

    notify_list_changed(lst, subject="Cost recalculated")

    # Only one notification (to the owner), not two.
    assert Notification.objects.filter(owner=user).count() == 1


@pytest.mark.django_db
def test_notify_list_changed_non_campaign_list_only_notifies_owner(user, make_list):
    lst = make_list("Gang")  # not in campaign mode
    notify_list_changed(lst, subject="Changed")
    assert Notification.objects.filter(owner=user).count() == 1


@pytest.mark.django_db
def test_notify_many_dedupes_and_returns_count(make_user):
    a = make_user("a", "password")
    b = make_user("b", "password")
    count = notify_many([a, b, a, None], subject="Broadcast")
    assert count == 2
    assert Notification.objects.filter(owner=a).count() == 1
    assert Notification.objects.filter(owner=b).count() == 1


@pytest.mark.django_db
def test_notify_many_empty_returns_zero():
    assert notify_many([], subject="Nobody") == 0


@pytest.mark.django_db
def test_notify_many_batches_across_batch_size(make_user):
    users = [make_user(f"u{i}", "password") for i in range(5)]
    # batch_size=2 forces multiple bulk_create batches.
    count = notify_many(users, subject="Batched", batch_size=2)
    assert count == 5
    assert Notification.objects.filter(subject="Batched").count() == 5


@pytest.mark.django_db
def test_notification_has_no_history_table():
    # Deliberate: notifications omit HistoricalRecords (see model docstring).
    assert hasattr(Notification, "history") is False


@pytest.mark.django_db
def test_mark_read_and_unread_are_idempotent(user):
    n = notify(recipient=user, subject="X")
    assert n.is_read is False
    n.mark_read()
    n.refresh_from_db()
    assert n.is_read is True
    assert n.read_at is not None
    # Idempotent — marking read again doesn't change read_at semantics or raise.
    prior = n.read_at
    n.mark_read()
    assert n.read_at == prior

    n.mark_unread()
    n.refresh_from_db()
    assert n.is_read is False
    assert n.read_at is None


@pytest.mark.django_db
def test_queryset_buckets_and_counts(user, make_user):
    other = make_user("other", "password")
    notify(recipient=user, subject="unread-1")
    read = notify(recipient=user, subject="read-1")
    read.mark_read()
    arch = notify(recipient=user, subject="archived-1")
    arch.archive()
    deleted = notify(recipient=user, subject="deleted-1")
    Notification.objects.filter(pk=deleted.pk).update(deleted_at="2026-01-01T00:00:00Z")
    notify(recipient=other, subject="other-user")

    qs = Notification.objects
    # Unread badge count: only the single active unread row for `user`.
    assert qs.unread_count_for(user) == 1
    # Active bucket excludes archived and deleted.
    assert qs.for_recipient(user).active().count() == 2  # unread + read
    assert qs.for_recipient(user).archived_bucket().count() == 1
    # Scoped to recipient.
    assert qs.unread_count_for(other) == 1


@pytest.mark.django_db
def test_banners_for_filters(user, make_list, make_campaign):
    lst = make_list("Gang")
    other_list = make_list("Other Gang")
    notify_list_owner(lst, subject="banner", show_as_banner=True)
    notify_list_owner(lst, subject="not-a-banner", show_as_banner=False)
    notify_list_owner(other_list, subject="other-list-banner", show_as_banner=True)

    banners = Notification.objects.banners_for(user, list_=lst)
    assert banners.count() == 1
    assert banners.first().subject == "banner"
