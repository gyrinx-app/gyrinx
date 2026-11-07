"""Expose edition maintenance and notification routes to the task registry."""

from n26.maintenance import task_routes as maintenance_routes
from n26.notifications import task_routes as notification_routes

task_routes = [*maintenance_routes, *notification_routes]

__all__ = ["task_routes"]
