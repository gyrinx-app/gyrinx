"""Task lookup and enumeration through the registered route list."""

from unittest.mock import patch

import pytest

from gyrinx.tasks import TaskRoute
from gyrinx.tasks.registry import get_all_tasks, get_task

pytestmark = pytest.mark.core


def sample_task():
    pass


def other_task():
    pass


def test_get_task_returns_none_for_unknown():

    result = get_task("nonexistent_task_xyz")
    assert result is None


def test_get_all_tasks_returns_list():

    result = get_all_tasks()
    assert isinstance(result, list)


def test_get_task_with_registered_task():

    routes = [TaskRoute(sample_task), TaskRoute(other_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = get_task("sample_task")
        assert result is not None
        assert result.name == "sample_task"

        result = get_task("other_task")
        assert result is not None
        assert result.name == "other_task"


def test_get_all_tasks_with_registered_tasks():

    routes = [TaskRoute(sample_task), TaskRoute(other_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = get_all_tasks()
        assert len(result) == 2
        names = [r.name for r in result]
        assert "sample_task" in names
        assert "other_task" in names
