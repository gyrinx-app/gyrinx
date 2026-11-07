"""
Django app configuration for tasks.
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class TasksConfig(AppConfig):
    """App configuration for background tasks."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "gyrinx.tasks"
    verbose_name = "Background Tasks"

    def ready(self):
        """Register lifecycle signal handlers and task-registration checks.

        Keep blocking Pub/Sub provisioning out of Django startup and request
        workers. docker/entrypoint.sh runs manage provision_tasks separately.
        """
        from gyrinx.tasks import signals  # noqa: F401  # isort: skip

        # Import the check module to register task-route validation with Django.
        from gyrinx.tasks import checks  # noqa: F401  # isort: skip
