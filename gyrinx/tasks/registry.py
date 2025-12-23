"""
Task Registry - Explicit task registration.

Add your tasks here, similar to Django's urlpatterns.

Usage:
    from gyrinx.tasks import TaskRoute
    from gyrinx.core.tasks import send_welcome_email, generate_report

    tasks = [
        TaskRoute(send_welcome_email),
        TaskRoute(generate_report, ack_deadline=600),
    ]

Note: Task imports are done lazily in _get_tasks() to avoid circular imports
during Django startup. The backend imports this module before Django's task
framework is fully initialized.
"""

from gyrinx.tasks import TaskRoute

# Cache for lazily-loaded tasks
_tasks: list[TaskRoute] | None = None


def _get_tasks() -> list[TaskRoute]:
    """
    Lazily load and cache the task list.

    This avoids circular imports that occur when importing task functions
    at module level (gyrinx.core.tasks uses @task decorator from django.tasks,
    which triggers backend loading, which imports this registry).
    """
    global _tasks
    if _tasks is None:
        from gyrinx.core.tasks import (
            backfill_list_action,
            hello_world,
            refresh_list_facts,
        )

        _tasks = [
            TaskRoute(hello_world),
            TaskRoute(refresh_list_facts),
            # Backfill task: longer ack_deadline since it does facts_from_db
            # which can be expensive for large lists. Longer retry delays
            # to naturally throttle processing rate.
            TaskRoute(
                backfill_list_action,
                ack_deadline=300,  # 5 minutes to complete
                min_retry_delay=30,  # Wait 30s before retry
                max_retry_delay=600,  # Max 10 min backoff
            ),
        ]
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
