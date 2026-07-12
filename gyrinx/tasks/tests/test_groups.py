"""Tests for the generic task-group machinery: enqueue_in_group, group_status, and the poll view.

A single logical operation often fans out into many background task runs tagged with a shared
``group_key`` (e.g. starting a campaign spawns one clone task per gang, #1222). The
``/tasks/status`` endpoint reports the group's rollup so a UI can poll it. These tests exercise
the generic plumbing independently of any one feature.
"""

from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from gyrinx.tasks.groups import enqueue_in_group, group_status
from gyrinx.tasks.models import TaskExecution


def _mk(task_id, group_key, *, status="READY", label=""):
    """Create a TaskExecution row directly, in a chosen state."""
    return TaskExecution.objects.create(
        task_id=task_id,
        task_name="test_task",
        group_key=group_key,
        label=label,
        status=status,
        enqueued_at=timezone.now(),
    )


# =============================================================================
# group_status()
# =============================================================================


@pytest.mark.django_db
def test_group_status_empty_group_is_not_complete():
    """A group with no task runs is not 'complete' — nothing has been enqueued yet."""
    data = group_status("nonexistent")
    assert data["group"] == "nonexistent"
    assert data["complete"] is False
    assert data["counts"]["total"] == 0
    assert data["units"] == []


@pytest.mark.django_db
def test_group_status_counts_and_incomplete_while_pending():
    """Mixed states roll up correctly; the group is incomplete while any unit is pending."""
    g = "op:1"
    _mk("t1", g, status="SUCCESSFUL", label="A")
    _mk("t2", g, status="RUNNING", label="B")
    _mk("t3", g, status="READY", label="C")
    # A row in a different group must not leak into this one's rollup.
    _mk("other", "op:2", status="FAILED")

    data = group_status(g)
    assert data["counts"] == {
        "total": 3,
        "successful": 1,
        "failed": 0,
        "running": 1,
        "ready": 1,
        "pending": 2,
    }
    assert data["complete"] is False
    assert {u["label"] for u in data["units"]} == {"A", "B", "C"}
    # Only non-sensitive fields are exposed (never args/kwargs/tracebacks).
    assert all(set(u) == {"task_id", "label", "status"} for u in data["units"])


@pytest.mark.django_db
def test_group_status_complete_when_all_terminal():
    """A group is complete once every unit is terminal (successful or failed)."""
    g = "op:done"
    _mk("t1", g, status="SUCCESSFUL")
    _mk("t2", g, status="FAILED")

    data = group_status(g)
    assert data["complete"] is True
    assert data["counts"]["pending"] == 0
    assert data["counts"]["successful"] == 1
    assert data["counts"]["failed"] == 1


# =============================================================================
# enqueue_in_group()
# =============================================================================


@pytest.mark.django_db
def test_enqueue_in_group_tags_the_task_execution_row():
    """enqueue_in_group stamps the row the enqueue created with group_key + label."""
    # Simulate the row the task_enqueued signal creates during enqueue.
    row = _mk("task-xyz", "")

    fake_task = mock.Mock()
    fake_task.enqueue.return_value = mock.Mock(id="task-xyz")

    result = enqueue_in_group(
        fake_task, group_key="op:tagged", label="Gang 7", foo="bar"
    )

    # kwargs are forwarded verbatim; group_key/label are not.
    fake_task.enqueue.assert_called_once_with(foo="bar")
    assert result is fake_task.enqueue.return_value
    row.refresh_from_db()
    assert row.group_key == "op:tagged"
    assert row.label == "Gang 7"


@pytest.mark.django_db
def test_enqueue_in_group_skips_tagging_when_enqueue_returns_no_id():
    """If enqueue yields no result/id there's nothing to tag — and it must not raise."""
    fake_task = mock.Mock()
    fake_task.enqueue.return_value = None

    result = enqueue_in_group(fake_task, group_key="op:x", label="y", a=1)

    fake_task.enqueue.assert_called_once_with(a=1)
    assert result is None


# =============================================================================
# task_group_status view (GET /tasks/status)
# =============================================================================


@pytest.mark.django_db
def test_group_status_view_requires_group_param(client):
    """Missing the 'group' query parameter is a 400."""
    resp = client.get(reverse("tasks:group-status"))
    assert resp.status_code == 400


@pytest.mark.django_db
def test_group_status_view_is_public_and_returns_json(client):
    """The endpoint is readable without authentication and returns the group rollup."""
    g = "op:public"
    _mk("t1", g, status="SUCCESSFUL", label="A")
    _mk("t2", g, status="READY", label="B")

    # `client` is anonymous (not logged in).
    resp = client.get(reverse("tasks:group-status"), {"group": g})
    assert resp.status_code == 200
    data = resp.json()
    assert data["group"] == g
    assert data["counts"]["total"] == 2
    assert data["complete"] is False
    # Never leak sensitive task fields.
    for unit in data["units"]:
        assert set(unit) == {"task_id", "label", "status"}
