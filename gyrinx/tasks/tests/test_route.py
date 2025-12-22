"""
Tests for TaskRoute configuration.
"""

from django.test import override_settings

from gyrinx.tasks import TaskRoute


def sample_task():
    """A sample task function for testing."""
    pass


def test_task_route_name():
    """TaskRoute.name returns the function name."""
    route = TaskRoute(sample_task)
    assert route.name == "sample_task"


def test_task_route_path():
    """TaskRoute.path returns the full module path."""
    route = TaskRoute(sample_task)
    assert route.path == "gyrinx.tasks.tests.test_route.sample_task"


@override_settings(TASKS_ENVIRONMENT="prod")
def test_task_route_topic_name_prod():
    """TaskRoute.topic_name includes environment prefix."""
    route = TaskRoute(sample_task)
    assert (
        route.topic_name
        == "prod--gyrinx.tasks--gyrinx.tasks.tests.test_route.sample_task"
    )


@override_settings(TASKS_ENVIRONMENT="staging")
def test_task_route_topic_name_staging():
    """TaskRoute.topic_name uses configured environment."""
    route = TaskRoute(sample_task)
    assert (
        route.topic_name
        == "staging--gyrinx.tasks--gyrinx.tasks.tests.test_route.sample_task"
    )


def test_task_route_defaults():
    """TaskRoute has sensible defaults."""
    route = TaskRoute(sample_task)
    assert route.ack_deadline == 300
    assert route.min_retry_delay == 10
    assert route.max_retry_delay == 600


def test_task_route_custom_config():
    """TaskRoute accepts custom configuration."""
    route = TaskRoute(
        sample_task,
        ack_deadline=600,
        min_retry_delay=30,
        max_retry_delay=1200,
    )
    assert route.ack_deadline == 600
    assert route.min_retry_delay == 30
    assert route.max_retry_delay == 1200


def test_task_route_repr():
    """TaskRoute has a useful repr."""
    route = TaskRoute(sample_task, ack_deadline=120)
    assert "sample_task" in repr(route)
    assert "120" in repr(route)
