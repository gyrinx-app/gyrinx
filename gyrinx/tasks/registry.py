"""Collect task routes declared by installed apps.

Apps export a task_routes list from their tasks module. Discovery in
gyrinx.tasks.discovery supplies routes to backends and provisioning;
the registry declares no edition-specific tasks.
"""

from gyrinx.tasks.discovery import discover_task_routes
from gyrinx.tasks.route import TaskRoute

_tasks: list[TaskRoute] | None = None


def _get_tasks() -> list[TaskRoute]:
    """Discover and cache routes on first lookup.

    Import-time discovery would re-enter this module through @task and its
    backend, and would run before Django has populated the app registry.
    """
    global _tasks
    if _tasks is None:
        _tasks = discover_task_routes()
    return _tasks


def get_task(name: str) -> TaskRoute | None:
    """Return the route with this function name, or None if none is registered."""
    for route in _get_tasks():
        if route.name == name:
            return route
    return None


def get_all_tasks() -> list[TaskRoute]:
    """Get all registered tasks."""
    return _get_tasks()
