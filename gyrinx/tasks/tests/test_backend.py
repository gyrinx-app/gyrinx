"""
Tests for the PubSubBackend task result persistence.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from django.tasks.base import TaskResultStatus

from gyrinx.tasks import TaskRoute
from gyrinx.tasks.backend import PubSubBackend
from gyrinx.tasks.models import TaskExecution


def _test_task(name: str = "World"):
    """A simple test task function."""
    return f"Hello, {name}!"


@pytest.fixture
def pubsub_backend():
    """Create a PubSubBackend instance for testing."""
    return PubSubBackend(
        "default",
        {"OPTIONS": {"project_id": "test-project"}},
    )


@pytest.fixture
def mock_publisher():
    """Mock the Pub/Sub publisher."""
    with patch.object(PubSubBackend, "publisher", new_callable=MagicMock):
        yield


# =============================================================================
# Backend Configuration Tests
# =============================================================================


def test_supports_get_result_is_true():
    """Backend should have supports_get_result = True."""
    assert PubSubBackend.supports_get_result is True


def test_backend_initialization(pubsub_backend):
    """Backend should initialize with correct project_id."""
    assert pubsub_backend.project_id == "test-project"


# =============================================================================
# Enqueue with Persistence Tests
# =============================================================================


@pytest.mark.django_db
def test_enqueue_creates_task_execution(pubsub_backend, mock_publisher):
    """TaskExecution record should be created on enqueue."""
    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    # Mock the publisher
    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {})

    # Verify TaskExecution was created
    execution = TaskExecution.objects.get(id=result.id)
    assert execution is not None


@pytest.mark.django_db
def test_enqueue_sets_task_name(pubsub_backend, mock_publisher):
    """task_name should match the function name."""
    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {})

    execution = TaskExecution.objects.get(id=result.id)
    assert execution.task_name == "_test_task"


@pytest.mark.django_db
def test_enqueue_sets_args(pubsub_backend, mock_publisher):
    """args should be stored as JSON list."""
    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, ("arg1", "arg2"), {})

    execution = TaskExecution.objects.get(id=result.id)
    assert execution.args == ["arg1", "arg2"]


@pytest.mark.django_db
def test_enqueue_sets_kwargs(pubsub_backend, mock_publisher):
    """kwargs should be stored as JSON dict."""
    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {"key": "value"})

    execution = TaskExecution.objects.get(id=result.id)
    assert execution.kwargs == {"key": "value"}


@pytest.mark.django_db
def test_enqueue_sets_enqueued_at(pubsub_backend, mock_publisher):
    """enqueued_at should be set on creation."""
    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {})

    execution = TaskExecution.objects.get(id=result.id)
    assert execution.enqueued_at is not None


@pytest.mark.django_db
def test_enqueue_sets_ready_status(pubsub_backend, mock_publisher):
    """status should be READY on creation."""
    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {})

    execution = TaskExecution.objects.get(id=result.id)
    assert execution.status == "READY"


@pytest.mark.django_db
def test_enqueue_returns_task_result(pubsub_backend, mock_publisher):
    """enqueue should return TaskResult with correct id."""
    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {})

    assert result is not None
    assert result.id is not None
    assert result.status == TaskResultStatus.READY


# =============================================================================
# Get Result Tests
# =============================================================================


@pytest.mark.django_db
def test_get_result_returns_task_result(pubsub_backend):
    """get_result should return TaskResult for existing task."""
    execution = TaskExecution.objects.create(
        task_name="test_task",
        args=[],
        kwargs={},
        enqueued_at=datetime.now(timezone.utc),
    )

    result = pubsub_backend.get_result(str(execution.id))

    assert result is not None
    assert result.id == str(execution.id)


@pytest.mark.django_db
def test_get_result_returns_none_for_missing(pubsub_backend):
    """get_result should return None for unknown task_id."""
    result = pubsub_backend.get_result("00000000-0000-0000-0000-000000000000")
    assert result is None


@pytest.mark.django_db
def test_get_result_status_ready(pubsub_backend):
    """READY status should map to TaskResultStatus.READY."""
    execution = TaskExecution.objects.create(
        task_name="test_task",
        status="READY",
        enqueued_at=datetime.now(timezone.utc),
    )

    result = pubsub_backend.get_result(str(execution.id))
    assert result.status == TaskResultStatus.READY


@pytest.mark.django_db
def test_get_result_status_running(pubsub_backend):
    """RUNNING status should map to TaskResultStatus.RUNNING."""
    execution = TaskExecution.objects.create(
        task_name="test_task",
        enqueued_at=datetime.now(timezone.utc),
    )
    execution.mark_running()

    result = pubsub_backend.get_result(str(execution.id))
    assert result.status == TaskResultStatus.RUNNING


@pytest.mark.django_db
def test_get_result_status_successful(pubsub_backend):
    """SUCCESSFUL status should map to TaskResultStatus.SUCCESSFUL."""
    execution = TaskExecution.objects.create(
        task_name="test_task",
        enqueued_at=datetime.now(timezone.utc),
    )
    execution.mark_running()
    execution.mark_successful()

    result = pubsub_backend.get_result(str(execution.id))
    assert result.status == TaskResultStatus.SUCCESSFUL


@pytest.mark.django_db
def test_get_result_status_failed(pubsub_backend):
    """FAILED status should map to TaskResultStatus.FAILED."""
    execution = TaskExecution.objects.create(
        task_name="test_task",
        enqueued_at=datetime.now(timezone.utc),
    )
    execution.mark_failed(error_message="Test error")

    result = pubsub_backend.get_result(str(execution.id))
    assert result.status == TaskResultStatus.FAILED


@pytest.mark.django_db
def test_get_result_includes_timing_fields(pubsub_backend):
    """Result should include enqueued_at, started_at, finished_at."""
    execution = TaskExecution.objects.create(
        task_name="test_task",
        enqueued_at=datetime.now(timezone.utc),
    )
    execution.mark_running()
    execution.mark_successful()

    result = pubsub_backend.get_result(str(execution.id))

    assert result.enqueued_at == execution.enqueued_at
    assert result.started_at == execution.started_at
    assert result.finished_at == execution.finished_at


@pytest.mark.django_db
def test_get_result_includes_args_kwargs(pubsub_backend):
    """Result should include args and kwargs."""
    execution = TaskExecution.objects.create(
        task_name="test_task",
        args=["arg1"],
        kwargs={"key": "value"},
        enqueued_at=datetime.now(timezone.utc),
    )

    result = pubsub_backend.get_result(str(execution.id))

    assert result.args == ["arg1"]
    assert result.kwargs == {"key": "value"}


@pytest.mark.django_db
def test_get_result_includes_error_message(pubsub_backend):
    """Failed result should include error message in errors list."""
    execution = TaskExecution.objects.create(
        task_name="test_task",
        enqueued_at=datetime.now(timezone.utc),
    )
    execution.mark_failed(error_message="Something went wrong")

    result = pubsub_backend.get_result(str(execution.id))

    assert "Something went wrong" in result.errors
