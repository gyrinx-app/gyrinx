"""PubSubBackend execution persistence and TaskResult reconstruction."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from django.tasks.base import TaskResultStatus

from gyrinx.tasks import TaskRoute
from gyrinx.tasks.backend import PubSubBackend
from gyrinx.tasks.models import TaskExecution

pytestmark = pytest.mark.core


def make_task_id():
    """Generate a unique task ID for tests."""
    return f"test-task-{uuid.uuid4()}"


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


def test_supports_get_result_is_true():

    assert PubSubBackend.supports_get_result is True


def test_backend_initialization(pubsub_backend):

    assert pubsub_backend.project_id == "test-project"


@pytest.mark.django_db
def test_enqueue_creates_task_execution(pubsub_backend, mock_publisher):

    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {})

    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution is not None


@pytest.mark.django_db
def test_enqueue_sets_task_name(pubsub_backend, mock_publisher):

    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {})

    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.task_name == "_test_task"


@pytest.mark.django_db
def test_enqueue_sets_args(pubsub_backend, mock_publisher):

    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, ("arg1", "arg2"), {})

    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.args == ["arg1", "arg2"]


@pytest.mark.django_db
def test_enqueue_sets_kwargs(pubsub_backend, mock_publisher):

    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {"key": "value"})

    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.kwargs == {"key": "value"}


@pytest.mark.django_db
def test_enqueue_sets_enqueued_at(pubsub_backend, mock_publisher):

    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {})

    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.enqueued_at is not None


@pytest.mark.django_db
def test_enqueue_sets_ready_status(pubsub_backend, mock_publisher):

    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"

    mock_future = MagicMock()
    pubsub_backend.publisher.publish.return_value = mock_future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    routes = [TaskRoute(_test_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = pubsub_backend.enqueue(mock_task, (), {})

    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "READY"


@pytest.mark.django_db
def test_enqueue_returns_task_result(pubsub_backend, mock_publisher):

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


@pytest.mark.django_db
def test_confirmed_route_propagates_publish_failure(pubsub_backend, mock_publisher):
    mock_task = MagicMock()
    mock_task.func.__name__ = "_test_task"
    future = MagicMock()
    future.result.side_effect = RuntimeError("publish failed")
    pubsub_backend.publisher.publish.return_value = future
    pubsub_backend.publisher.topic_path.return_value = "projects/test/topics/test"

    with patch(
        "gyrinx.tasks.registry._tasks", [TaskRoute(_test_task, confirm_publish=True)]
    ):
        with pytest.raises(RuntimeError, match="publish failed"):
            pubsub_backend.enqueue(mock_task, (), {})

    future.result.assert_called_once_with(timeout=10)


@pytest.mark.django_db
def test_get_result_returns_task_result(pubsub_backend):

    task_id = make_task_id()
    TaskExecution.objects.create(
        task_id=task_id,
        task_name="test_task",
        args=[],
        kwargs={},
        enqueued_at=datetime.now(UTC),
    )

    result = pubsub_backend.get_result(task_id)

    assert result is not None
    assert result.id == task_id


@pytest.mark.django_db
def test_get_result_returns_none_for_missing(pubsub_backend):

    result = pubsub_backend.get_result("nonexistent-task-id")
    assert result is None


@pytest.mark.django_db
def test_get_result_status_ready(pubsub_backend):

    task_id = make_task_id()
    TaskExecution.objects.create(
        task_id=task_id,
        task_name="test_task",
        status="READY",
        enqueued_at=datetime.now(UTC),
    )

    result = pubsub_backend.get_result(task_id)
    assert result.status == TaskResultStatus.READY


@pytest.mark.django_db
def test_get_result_status_running(pubsub_backend):

    task_id = make_task_id()
    execution = TaskExecution.objects.create(
        task_id=task_id,
        task_name="test_task",
        enqueued_at=datetime.now(UTC),
    )
    execution.mark_running()

    result = pubsub_backend.get_result(task_id)
    assert result.status == TaskResultStatus.RUNNING


@pytest.mark.django_db
def test_get_result_status_successful(pubsub_backend):

    task_id = make_task_id()
    execution = TaskExecution.objects.create(
        task_id=task_id,
        task_name="test_task",
        enqueued_at=datetime.now(UTC),
    )
    execution.mark_running()
    execution.mark_successful()

    result = pubsub_backend.get_result(task_id)
    assert result.status == TaskResultStatus.SUCCESSFUL


@pytest.mark.django_db
def test_get_result_status_failed(pubsub_backend):

    task_id = make_task_id()
    execution = TaskExecution.objects.create(
        task_id=task_id,
        task_name="test_task",
        enqueued_at=datetime.now(UTC),
    )
    execution.mark_failed(error_message="Test error")

    result = pubsub_backend.get_result(task_id)
    assert result.status == TaskResultStatus.FAILED


@pytest.mark.django_db
def test_get_result_includes_timing_fields(pubsub_backend):

    task_id = make_task_id()
    execution = TaskExecution.objects.create(
        task_id=task_id,
        task_name="test_task",
        enqueued_at=datetime.now(UTC),
    )
    execution.mark_running()
    execution.mark_successful()

    result = pubsub_backend.get_result(task_id)

    assert result.enqueued_at == execution.enqueued_at
    assert result.started_at == execution.started_at
    assert result.finished_at == execution.finished_at


@pytest.mark.django_db
def test_get_result_includes_args_kwargs(pubsub_backend):

    task_id = make_task_id()
    TaskExecution.objects.create(
        task_id=task_id,
        task_name="test_task",
        args=["arg1"],
        kwargs={"key": "value"},
        enqueued_at=datetime.now(UTC),
    )

    result = pubsub_backend.get_result(task_id)

    assert result.args == ["arg1"]
    assert result.kwargs == {"key": "value"}


@pytest.mark.django_db
def test_get_result_includes_error_message(pubsub_backend):

    task_id = make_task_id()
    execution = TaskExecution.objects.create(
        task_id=task_id,
        task_name="test_task",
        enqueued_at=datetime.now(UTC),
    )
    execution.mark_failed(error_message="Something went wrong")

    result = pubsub_backend.get_result(task_id)

    assert "Something went wrong" in result.errors
