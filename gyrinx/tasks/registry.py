"""
Task Registry - the collected view of every app's task routes.

Apps declare their own routes in their own ``<app>/tasks.py``, as a module-level
``task_routes`` list:

    from django.tasks import task
    from gyrinx.tasks import TaskRoute

    @task
    def send_welcome_email(user_id: int): ...

    task_routes = [
        TaskRoute(send_welcome_email),
        TaskRoute(generate_report, ack_deadline=600),
    ]

This module collects them (see ``gyrinx.tasks.discovery``) and offers the lookup
helpers the backends and provisioning use. It names no tasks itself: the
platform should not have to know what an edition calls its work (#2093).
"""

from gyrinx.tasks.discovery import discover_task_routes
from gyrinx.tasks.route import TaskRoute

# Cache for the lazily-discovered routes.
_tasks: list[TaskRoute] | None = None


def _get_tasks() -> list[TaskRoute]:
    """
    Discover the routes on first use, then cache them.

    Discovery must not run at this module's import time, for two independent
    reasons:

    1. **Circular import.** Importing an app's ``tasks`` module runs Django's
       ``@task`` decorator, which loads the configured task backend, which does
       ``from gyrinx.tasks.registry import get_task`` at module scope. Pulling
       the app modules in from here at import time would re-enter this module
       while it is still half-built.
    2. **The app registry.** Discovery walks ``django.apps``, which is only
       populated once Django has loaded every app — later than this module is
       first imported.

    Deferring to first call sidesteps both: by the time anything asks for a
    route, the apps are loaded and the backend is fully imported.
    """
    global _tasks
    if _tasks is None:
        _tasks = discover_task_routes()
    return _tasks


# =============================================================================
# Registry helpers (don't edit below)
# =============================================================================


def get_task(name: str) -> TaskRoute | None:
    """
    Get task route by function name.

    Args:
        name: The task function name (e.g., 'send_welcome_email')

    Returns:
        TaskRoute if found, None otherwise
    """
    for route in _get_tasks():
        if route.name == name:
            return route
    return None


def get_all_tasks() -> list[TaskRoute]:
    """Get all registered tasks."""
    return _get_tasks()
