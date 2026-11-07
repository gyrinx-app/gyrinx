"""The production legacy-key cleanup commits bounded, replay-safe batches."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.urls import reverse

from gyrinx.analytics.models import Event, EventVerb
from gyrinx.analytics.nouns import PlatformNoun
from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.tasks import (
    SESSION_SCRUB_OPERATION,
    count_legacy_session_keys,
    scrub_event_sessions,
)


@pytest.fixture
def legacy_events():
    """The --nomigrations test schema omits the compatibility-only column."""
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE core_event ADD COLUMN session_id varchar(40)")
    user = get_user_model().objects.create_user(username="session-scrub-test")
    for _ in range(5):
        event = Event.objects.create(
            owner=user, noun=PlatformNoun.USER, verb=EventVerb.LOGIN
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE core_event SET session_id = %s WHERE id = %s",
                ["synthetic-test-key", event.pk],
            )
    yield user
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE core_event DROP COLUMN session_id")


@pytest.mark.django_db(transaction=True)
def test_scrub_batches_resume_and_duplicate_delivery_is_harmless(legacy_events):
    record = Backfill.objects.create(
        operation=SESSION_SCRUB_OPERATION,
        status=Backfill.Status.RUNNING,
    )
    assert count_legacy_session_keys() == 5

    with patch("django.tasks.base.Task.enqueue") as enqueue:
        scrub_event_sessions.func(backfill_id=str(record.pk), batch_size=2)
        record.refresh_from_db()
        assert record.summary["cleared"] == 2
        assert record.summary["remaining"] == 3
        assert record.status == Backfill.Status.RUNNING
        assert enqueue.call_count == 1

        scrub_event_sessions.func(backfill_id=str(record.pk), batch_size=2)
        scrub_event_sessions.func(backfill_id=str(record.pk), batch_size=2)
        scrub_event_sessions.func(backfill_id=str(record.pk), batch_size=2)
        record.refresh_from_db()

    assert record.status == Backfill.Status.DONE
    assert record.summary["cleared"] == 5
    assert record.summary["remaining"] == 0
    assert count_legacy_session_keys() == 0
    assert enqueue.call_count == 3
    enqueue.assert_any_call(backfill_id=str(record.pk), batch_size=2)


@pytest.mark.django_db(transaction=True)
def test_admin_preview_and_trigger_record_the_job(legacy_events):
    user = legacy_events
    user.is_staff = user.is_superuser = True
    user.save()
    client = Client()
    client.force_login(user)
    url = reverse("admin:maintenance_scrub_event_sessions")

    response = client.get(url)
    assert response.status_code == 200
    assert b"5 Event records" in response.content

    with patch("django.tasks.base.Task.enqueue") as enqueue:
        response = client.post(url)

    record = Backfill.objects.get(operation=SESSION_SCRUB_OPERATION)
    assert response.status_code == 302
    assert record.triggered_by == user
    assert record.status == Backfill.Status.RUNNING
    assert record.summary["total"] == 5
    enqueue.assert_called_once_with(backfill_id=str(record.pk))


@pytest.mark.django_db(transaction=True)
def test_failed_continuation_keeps_progress_for_pubsub_retry(legacy_events):
    record = Backfill.objects.create(
        operation=SESSION_SCRUB_OPERATION,
        status=Backfill.Status.RUNNING,
    )

    with patch(
        "django.tasks.base.Task.enqueue", side_effect=RuntimeError("publish failed")
    ):
        with pytest.raises(RuntimeError, match="publish failed"):
            scrub_event_sessions.func(backfill_id=str(record.pk), batch_size=2)

    record.refresh_from_db()
    assert record.status == Backfill.Status.RUNNING
    assert record.summary["cleared"] == 2
    assert count_legacy_session_keys() == 3

    with patch("django.tasks.base.Task.enqueue"):
        scrub_event_sessions.func(backfill_id=str(record.pk), batch_size=2)
    record.refresh_from_db()
    assert record.summary["cleared"] == 4


@pytest.mark.django_db(transaction=True)
def test_failed_initial_publish_marks_job_failed(legacy_events):
    user = legacy_events
    user.is_staff = user.is_superuser = True
    user.save()
    client = Client()
    client.force_login(user)

    with patch(
        "django.tasks.base.Task.enqueue", side_effect=RuntimeError("publish failed")
    ):
        response = client.post(reverse("admin:maintenance_scrub_event_sessions"))

    record = Backfill.objects.get(operation=SESSION_SCRUB_OPERATION)
    assert response.status_code == 302
    assert record.status == Backfill.Status.FAILED
    assert record.error == "The cleanup task could not be queued."
    assert count_legacy_session_keys() == 5
