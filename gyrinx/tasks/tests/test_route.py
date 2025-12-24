"""
Tests for TaskRoute configuration.
"""

import pytest
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


def test_task_route_no_schedule_by_default():
    """TaskRoute has no schedule by default."""
    route = TaskRoute(sample_task)
    assert route.schedule is None
    assert route.is_scheduled is False


def test_task_route_with_schedule():
    """TaskRoute accepts a schedule."""
    route = TaskRoute(sample_task, schedule="0 3 * * *")
    assert route.schedule == "0 3 * * *"
    assert route.is_scheduled is True


def test_task_route_schedule_timezone_default():
    """TaskRoute schedule_timezone defaults to UTC."""
    route = TaskRoute(sample_task, schedule="0 3 * * *")
    assert route.schedule_timezone == "UTC"


def test_task_route_schedule_timezone_custom():
    """TaskRoute accepts custom schedule_timezone."""
    route = TaskRoute(
        sample_task, schedule="0 9 * * *", schedule_timezone="Europe/London"
    )
    assert route.schedule_timezone == "Europe/London"


@override_settings(TASKS_ENVIRONMENT="prod")
def test_task_route_scheduler_job_name():
    """TaskRoute.scheduler_job_name includes environment prefix."""
    route = TaskRoute(sample_task, schedule="0 3 * * *")
    assert (
        route.scheduler_job_name
        == "prod--gyrinx-scheduler--gyrinx.tasks.tests.test_route.sample_task"
    )


def test_task_route_scheduler_job_name_requires_schedule():
    """TaskRoute.scheduler_job_name raises if no schedule configured."""
    route = TaskRoute(sample_task)
    with pytest.raises(ValueError, match="no schedule configured"):
        _ = route.scheduler_job_name


def test_task_route_validates_cron_on_creation():
    """TaskRoute validates cron expression format on creation."""
    # Valid cron expressions should work
    TaskRoute(sample_task, schedule="0 3 * * *")
    TaskRoute(sample_task, schedule="*/10 * * * *")
    TaskRoute(sample_task, schedule="0 0 1 * *")
    TaskRoute(sample_task, schedule="30 4 1,15 * 0-6")


def test_task_route_rejects_invalid_cron():
    """TaskRoute raises ValueError for invalid cron expressions."""
    with pytest.raises(ValueError, match="Invalid cron expression"):
        TaskRoute(sample_task, schedule="invalid")

    with pytest.raises(ValueError, match="Invalid cron expression"):
        TaskRoute(sample_task, schedule="* * *")  # Only 3 fields

    with pytest.raises(ValueError, match="Invalid cron expression"):
        TaskRoute(sample_task, schedule="* * * * * *")  # 6 fields


def test_task_route_repr_without_schedule():
    """TaskRoute repr shows name and ack_deadline when no schedule."""
    route = TaskRoute(sample_task, ack_deadline=120)
    assert repr(route) == "TaskRoute(sample_task, ack_deadline=120)"


def test_task_route_repr_with_schedule():
    """TaskRoute repr includes schedule when present."""
    route = TaskRoute(sample_task, schedule="0 3 * * *")
    assert "schedule='0 3 * * *'" in repr(route)
    assert "sample_task" in repr(route)
