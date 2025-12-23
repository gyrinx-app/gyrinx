"""
Tests for task registry.
"""

from unittest.mock import patch

from gyrinx.tasks import TaskRoute
from gyrinx.tasks.registry import get_all_tasks, get_task


def sample_task():
    pass


def other_task():
    pass


def test_get_task_returns_none_for_unknown():
    """get_task returns None for unknown task names."""
    result = get_task("nonexistent_task_xyz")
    assert result is None


def test_get_all_tasks_returns_list():
    """get_all_tasks returns a list."""
    result = get_all_tasks()
    assert isinstance(result, list)


def test_get_task_with_registered_task():
    """get_task returns the route for registered tasks."""
    routes = [TaskRoute(sample_task), TaskRoute(other_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = get_task("sample_task")
        assert result is not None
        assert result.name == "sample_task"

        result = get_task("other_task")
        assert result is not None
        assert result.name == "other_task"


def test_get_all_tasks_with_registered_tasks():
    """get_all_tasks returns all registered tasks."""
    routes = [TaskRoute(sample_task), TaskRoute(other_task)]
    with patch("gyrinx.tasks.registry._tasks", routes):
        result = get_all_tasks()
        assert len(result) == 2
        names = [r.name for r in result]
        assert "sample_task" in names
        assert "other_task" in names
