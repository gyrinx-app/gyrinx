"""
Tests for the Pub/Sub push handler view.
"""

import base64
import json
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


@pytest.mark.django_db
def test_pubsub_handler_rejects_get(client):
    """GET requests should return 405."""
    url = reverse("tasks:pubsub")
    response = client.get(url)
    assert response.status_code == 405


@pytest.mark.django_db
def test_pubsub_handler_rejects_invalid_json(client):
    """Invalid JSON should return 400."""
    url = reverse("tasks:pubsub")
    response = client.post(url, data="not json", content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_pubsub_handler_rejects_missing_data(client):
    """Missing data field should return 400."""
    url = reverse("tasks:pubsub")
    response = client.post(
        url,
        data=json.dumps({"message": {}}),
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_pubsub_handler_rejects_unknown_task(client):
    """Unknown task name should return 400."""
    url = reverse("tasks:pubsub")
    envelope = make_pubsub_message("nonexistent_task")
    response = client.post(
        url,
        data=json.dumps(envelope),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert b"Unknown task" in response.content


@pytest.mark.django_db
def test_pubsub_handler_rejects_missing_task_name(client):
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


def _test_task(name: str = "World"):
    """A simple test task function."""
    return f"Hello, {name}!"


@pytest.mark.django_db
def test_pubsub_handler_executes_registered_task(client):
    """Registered tasks should execute and return 200."""
    url = reverse("tasks:pubsub")
    routes = [TaskRoute(_test_task)]

    with patch("gyrinx.tasks.registry.tasks", routes):
        envelope = make_pubsub_message("_test_task", kwargs={"name": "Test"})
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 200
    assert response.content == b"OK"


@pytest.mark.django_db
def test_pubsub_handler_returns_500_on_task_error(client):
    """Task exceptions should return 500 for retry."""

    def failing_task():
        raise ValueError("Task failed!")

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(failing_task)]

    with patch("gyrinx.tasks.registry.tasks", routes):
        envelope = make_pubsub_message("failing_task")
        response = client.post(
            url,
            data=json.dumps(envelope),
            content_type="application/json",
        )

    assert response.status_code == 500
    assert b"Task failed" in response.content


@pytest.mark.django_db
def test_pubsub_handler_passes_args_and_kwargs(client):
    """Task should receive args and kwargs from message."""
    received = {}

    def capture_task(*args, **kwargs):
        received["args"] = args
        received["kwargs"] = kwargs

    url = reverse("tasks:pubsub")
    routes = [TaskRoute(capture_task)]

    with patch("gyrinx.tasks.registry.tasks", routes):
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
