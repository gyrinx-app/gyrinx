"""This app's background tasks, as the task registry expects to find them.

The registry reads ``task_routes`` from each app's ``tasks`` module. The
tasks themselves live in :mod:`n26.maintenance`, which is this edition's
one door onto the platform's maintenance console and task route — a task
declared here would be a second place importing them.
"""

from n26.maintenance import task_routes

__all__ = ["task_routes"]
