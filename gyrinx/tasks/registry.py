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
"""

from gyrinx.core.tasks import hello_world
from gyrinx.tasks import TaskRoute

# =============================================================================
# REGISTER YOUR TASKS HERE
# =============================================================================

# Example (uncomment when you have tasks):
# from gyrinx.core.tasks import send_welcome_email, generate_report
#
# tasks = [
#     TaskRoute(send_welcome_email),
#     TaskRoute(generate_report, ack_deadline=600, min_retry_delay=30),
# ]

tasks: list[TaskRoute] = [
    TaskRoute(hello_world),
]


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
    for route in tasks:
        if route.name == name:
            return route
    return None


def get_all_tasks() -> list[TaskRoute]:
    """Get all registered tasks."""
    return tasks
