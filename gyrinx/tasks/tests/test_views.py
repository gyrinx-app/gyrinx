"""
Tests for the Pub/Sub push handler view.
"""

import base64
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from gyrinx.tasks import TaskRoute


@pytest.fixture
def client():
    return Client()


def make_pubsub_message(task_name, task_id="test-123", args=None, kwargs=None):
    """Create a Pub/Sub push message envelope."""
    data = {
        "task_id": task_id,
        "task_name": task_name,
        "args": args or [],
        "kwargs": kwargs or {},
        "enqueued_at": "2025-01-01T00:00:00Z",
    }
    data_b64 = base64.b64encode(json.dumps(data).encode()).decode()
    return {
        "message": {
            "messageId": "msg-123",
            "data": data_b64,
        },
        "subscription": "projects/test/subscriptions/test-sub",
    }


def _test_task(name: str = "World"):
    """A simple test task function."""
    return f"Hello, {name}!"


@pytest.fixture
def bypass_oidc():
    """Fixture to bypass OIDC verification for tests."""
    with patch("gyrinx.tasks.views._verify_oidc_token", return_value=True):
        yield


# =============================================================================
# Basic Request Handling Tests (with OIDC bypassed)
# =============================================================================


@pytest.mark.django_db
def test_pubsub_handler_rejects_get(client, bypass_oidc):
    """GET requests should return 405."""
    url = reverse("tasks:pubsub")
    response = client.get(url)
    assert response.status_code == 405


@pytest.mark.django_db
def test_pubsub_handler_rejects_invalid_json(client, bypass_oidc):
    """Invalid JSON should return 400."""
    url = reverse("tasks:pubsub")
    response = client.post(url, data="not json", content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_pubsub_handler_rejects_missing_data(client, bypass_oidc):
    """Missing data field should return 400."""
    url = reverse("tasks:pubsub")
    response = client.post(
        url,
        data=json.dumps({"message": {}}),
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_pubsub_handler_rejects_unknown_task(client, bypass_oidc):
    """Unknown task name should return 400."""
    url = reverse("tasks:pubsub")
    envelope = make_pubsub_message("nonexistent_task")
    response = client.post(
        url,
        data=json.dumps(envelope),
        content_type="application/json",
    )
    assert response.status_code == 400
    # Error message should not include task name (security: prevent enumeration)
    assert response.content == b"Unknown task"


@pytest.mark.django_db
def test_pubsub_handler_rejects_missing_task_name(client, bypass_oidc):
    """Missing task_name should return 400."""
    url = reverse("tasks:pubsub")
    data = {
        "task_id": "test-123",
        "args": [],
        "kwargs": {},
    }
    data_b64 = base64.b64encode(json.dumps(data).encode()).decode()
    envelope = {
        "message": {
            "messageId": "msg-123",
            "data": data_b64,
        },
    }
    response = client.post(
        url,
        data=json.dumps(envelope),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert b"Missing task_name" in response.content


@pytest.mark.django_db
def test_pubsub_handler_executes_registered_task(client, bypass_oidc):
    """Registered tasks should execute and return 200."""
    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message("_test_task", kwargs={"name": "Test"})
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 200
    assert response.content == b"OK"


@pytest.mark.django_db
def test_pubsub_handler_returns_500_on_task_error(client, bypass_oidc):
    """Task exceptions should return 500 for retry."""

    def failing_task():
        raise ValueError("Task failed!")

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(failing_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message("failing_task")
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 500
    assert b"Task failed" in response.content


@pytest.mark.django_db
def test_pubsub_handler_passes_args_and_kwargs(client, bypass_oidc):
    """Task should receive args and kwargs from message."""
    received = {}

    def capture_task(*args, **kwargs):
        received["args"] = args
        received["kwargs"] = kwargs

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(capture_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "capture_task",
            args=["arg1", "arg2"],
            kwargs={"key1": "value1", "key2": 42},
        )
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 200
    assert received["args"] == ("arg1", "arg2")
    assert received["kwargs"] == {"key1": "value1", "key2": 42}


# =============================================================================
# OIDC Token Verification Tests
# =============================================================================


@pytest.mark.django_db
def test_pubsub_handler_rejects_when_oidc_fails(client):
    """Requests are rejected when OIDC verification fails."""
    url = reverse("tasks:pubsub")
    envelope = make_pubsub_message("_test_task")

    with patch("gyrinx.tasks.views._verify_oidc_token", return_value=False):
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 403
    assert response.content == b"Unauthorized"


@pytest.mark.django_db
def test_pubsub_handler_allows_when_oidc_succeeds(client):
    """Requests are allowed when OIDC verification succeeds."""
    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with (
        patch("gyrinx.tasks.views._verify_oidc_token", return_value=True),
        patch("gyrinx.tasks.registry._tasks", routes),
    ):
        envelope = make_pubsub_message("_test_task")
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 200


# =============================================================================
# Task Execution Status Update Tests
# =============================================================================


@pytest.fixture
def task_execution():
    """Create a TaskExecution record for testing."""
    from gyrinx.tasks.models import TaskExecution

    return TaskExecution.objects.create(
        id="550e8400-e29b-41d4-a716-446655440000",
        task_name="_test_task",
        args=[],
        kwargs={},
        enqueued_at=datetime.now(timezone.utc),
    )


@pytest.mark.django_db
def test_handler_transitions_to_running_on_start(client, bypass_oidc, task_execution):
    """Handler should transition TaskExecution to RUNNING when starting."""

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "_test_task",
            task_id=str(task_execution.id),
        )
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 200

    # Refresh and check status
    task_execution.refresh_from_db()
    # Should be SUCCESSFUL since task completed
    assert task_execution.status == "SUCCESSFUL"


@pytest.mark.django_db
def test_handler_sets_started_at_on_start(client, bypass_oidc, task_execution):
    """Handler should set started_at when task starts."""
    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "_test_task",
            task_id=str(task_execution.id),
        )
        client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    task_execution.refresh_from_db()
    assert task_execution.started_at is not None


@pytest.mark.django_db
def test_handler_transitions_to_successful_on_success(
    client, bypass_oidc, task_execution
):
    """Handler should transition TaskExecution to SUCCESSFUL on completion."""

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "_test_task",
            task_id=str(task_execution.id),
        )
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 200

    task_execution.refresh_from_db()
    assert task_execution.status == "SUCCESSFUL"


@pytest.mark.django_db
def test_handler_sets_finished_at_on_success(client, bypass_oidc, task_execution):
    """Handler should set finished_at when task completes."""
    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "_test_task",
            task_id=str(task_execution.id),
        )
        client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    task_execution.refresh_from_db()
    assert task_execution.finished_at is not None


@pytest.mark.django_db
def test_handler_stores_return_value_on_success(client, bypass_oidc, task_execution):
    """Handler should store return_value when task completes successfully."""
    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "_test_task",
            task_id=str(task_execution.id),
            kwargs={"name": "Test"},
        )
        client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    task_execution.refresh_from_db()
    assert task_execution.return_value == "Hello, Test!"


@pytest.mark.django_db
def test_handler_transitions_to_failed_on_error(client, bypass_oidc, task_execution):
    """Handler should transition TaskExecution to FAILED on error."""

    def failing_task():
        raise ValueError("Task failed!")

    # Update task_execution task_name to match
    task_execution.task_name = "failing_task"
    task_execution.save()

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(failing_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "failing_task",
            task_id=str(task_execution.id),
        )
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 500

    task_execution.refresh_from_db()
    assert task_execution.status == "FAILED"


@pytest.mark.django_db
def test_handler_stores_error_message_on_failure(client, bypass_oidc, task_execution):
    """Handler should store error_message when task fails."""

    def failing_task():
        raise ValueError("Something went wrong!")

    task_execution.task_name = "failing_task"
    task_execution.save()

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(failing_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "failing_task",
            task_id=str(task_execution.id),
        )
        client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    task_execution.refresh_from_db()
    assert "Something went wrong!" in task_execution.error_message


@pytest.mark.django_db
def test_handler_stores_error_traceback_on_failure(client, bypass_oidc, task_execution):
    """Handler should store error_traceback when task fails."""

    def failing_task():
        raise ValueError("Traceback test!")

    task_execution.task_name = "failing_task"
    task_execution.save()

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(failing_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "failing_task",
            task_id=str(task_execution.id),
        )
        client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    task_execution.refresh_from_db()
    assert "Traceback" in task_execution.error_traceback


@pytest.mark.django_db
def test_handler_missing_task_execution_continues(client, bypass_oidc):
    """Handler should continue execution if TaskExecution not found."""
    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        # Use a task_id that doesn't exist in the database
        envelope = make_pubsub_message(
            "_test_task",
            task_id="00000000-0000-0000-0000-000000000000",
        )
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    # Task should still execute successfully
    assert response.status_code == 200


@pytest.mark.django_db
def test_handler_creates_transition_records(client, bypass_oidc, task_execution):
    """Handler should create StateTransition records."""
    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "_test_task",
            task_id=str(task_execution.id),
        )
        client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    # Should have 2 transitions: READY -> RUNNING -> SUCCESSFUL
    transitions = list(task_execution.states.history)
    assert len(transitions) == 2


@pytest.mark.django_db
def test_full_task_lifecycle_success(client, bypass_oidc, task_execution):
    """Full successful task lifecycle should be tracked."""
    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    # Initial state
    assert task_execution.status == "READY"
    assert task_execution.started_at is None
    assert task_execution.finished_at is None

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "_test_task",
            task_id=str(task_execution.id),
        )
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 200

    # Final state
    task_execution.refresh_from_db()
    assert task_execution.status == "SUCCESSFUL"
    assert task_execution.started_at is not None
    assert task_execution.finished_at is not None
    assert task_execution.is_complete is True
    assert task_execution.is_success is True


@pytest.mark.django_db
def test_full_task_lifecycle_failure(client, bypass_oidc, task_execution):
    """Full failed task lifecycle should be tracked."""

    def failing_task():
        raise RuntimeError("Epic failure!")

    task_execution.task_name = "failing_task"
    task_execution.save()

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(failing_task)]

    with patch("gyrinx.tasks.registry._tasks", routes):
        envelope = make_pubsub_message(
            "failing_task",
            task_id=str(task_execution.id),
        )
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 500

    task_execution.refresh_from_db()
    assert task_execution.status == "FAILED"
    assert task_execution.started_at is not None
    assert task_execution.finished_at is not None
    assert task_execution.is_complete is True
    assert task_execution.is_failed is True
    assert "Epic failure!" in task_execution.error_message
