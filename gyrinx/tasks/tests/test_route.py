"""Task route names, delivery settings and schedule validation."""

import pytest
from django.test import override_settings

from gyrinx.tasks import TaskRoute
from gyrinx.tasks.route import PausedTaskConsumer

pytestmark = pytest.mark.core


def sample_task():
    """A sample task function for testing."""
    pass


def test_task_route_name():

    route = TaskRoute(sample_task)
    assert route.name == "sample_task"


def test_task_route_path():

    route = TaskRoute(sample_task)
    assert route.path == "gyrinx.tasks.tests.test_route.sample_task"


@override_settings(TASKS_ENVIRONMENT="prod")
def test_task_route_topic_name_prod():

    route = TaskRoute(sample_task)
    assert (
        route.topic_name
        == "prod--gyrinx.tasks--gyrinx.tasks.tests.test_route.sample_task"
    )


@override_settings(TASKS_ENVIRONMENT="staging")
def test_task_route_topic_name_staging():

    route = TaskRoute(sample_task)
    assert (
        route.topic_name
        == "staging--gyrinx.tasks--gyrinx.tasks.tests.test_route.sample_task"
    )


def test_task_route_defaults():

    route = TaskRoute(sample_task)
    assert route.ack_deadline == 300
    assert route.min_retry_delay == 10
    assert route.max_retry_delay == 600
    assert route.write_scope is None


def test_paused_consumer_requires_write_scope():
    with pytest.raises(ValueError, match="requires write_scope"):
        TaskRoute(sample_task, paused_consumer=PausedTaskConsumer())


def test_task_route_custom_config():

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

    route = TaskRoute(sample_task, ack_deadline=120)
    assert "sample_task" in repr(route)
    assert "120" in repr(route)


def test_task_route_no_schedule_by_default():

    route = TaskRoute(sample_task)
    assert route.schedule is None
    assert route.is_scheduled is False


def test_task_route_with_schedule():

    route = TaskRoute(sample_task, schedule="0 3 * * *")
    assert route.schedule == "0 3 * * *"
    assert route.is_scheduled is True


def test_task_route_schedule_timezone_default():

    route = TaskRoute(sample_task, schedule="0 3 * * *")
    assert route.schedule_timezone == "UTC"


def test_task_route_schedule_timezone_custom():

    route = TaskRoute(
        sample_task, schedule="0 9 * * *", schedule_timezone="Europe/London"
    )
    assert route.schedule_timezone == "Europe/London"


@override_settings(TASKS_ENVIRONMENT="prod")
def test_task_route_scheduler_job_name():

    route = TaskRoute(sample_task, schedule="0 3 * * *")
    assert (
        route.scheduler_job_name
        == "prod--gyrinx-scheduler--gyrinx-tasks-tests-test_route-sample_task"
    )


def test_task_route_scheduler_job_name_requires_schedule():

    route = TaskRoute(sample_task)
    with pytest.raises(ValueError, match="no schedule configured"):
        _ = route.scheduler_job_name


def test_task_route_validates_cron_on_creation():

    TaskRoute(sample_task, schedule="0 3 * * *")
    TaskRoute(sample_task, schedule="*/10 * * * *")
    TaskRoute(sample_task, schedule="0 0 1 * *")
    TaskRoute(sample_task, schedule="30 4 1,15 * 0-6")


def test_task_route_rejects_invalid_cron():

    with pytest.raises(ValueError, match="Invalid cron expression"):
        TaskRoute(sample_task, schedule="invalid")

    with pytest.raises(ValueError, match="Invalid cron expression"):
        TaskRoute(sample_task, schedule="* * *")  # Only 3 fields

    with pytest.raises(ValueError, match="Invalid cron expression"):
        TaskRoute(sample_task, schedule="* * * * * *")  # 6 fields


def test_task_route_repr_without_schedule():

    route = TaskRoute(sample_task, ack_deadline=120)
    assert repr(route) == "TaskRoute(sample_task, ack_deadline=120)"


def test_task_route_repr_with_schedule():

    route = TaskRoute(sample_task, schedule="0 3 * * *")
    assert "schedule='0 3 * * *'" in repr(route)
    assert "sample_task" in repr(route)


def test_task_route_validates_timezone_on_creation():

    TaskRoute(sample_task, schedule="0 3 * * *", schedule_timezone="UTC")
    TaskRoute(sample_task, schedule="0 3 * * *", schedule_timezone="Europe/London")
    TaskRoute(sample_task, schedule="0 3 * * *", schedule_timezone="America/New_York")


def test_task_route_rejects_invalid_timezone():

    with pytest.raises(ValueError, match="Invalid timezone"):
        TaskRoute(
            sample_task, schedule="0 3 * * *", schedule_timezone="Invalid/Timezone"
        )

    with pytest.raises(ValueError, match="Invalid timezone"):
        TaskRoute(sample_task, schedule="0 3 * * *", schedule_timezone="Europe/Londno")


def test_task_route_skips_timezone_validation_without_schedule():

    route = TaskRoute(sample_task, schedule_timezone="Invalid/Timezone")
    assert route.schedule_timezone == "Invalid/Timezone"
