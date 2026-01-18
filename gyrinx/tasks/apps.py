"""
Django app configuration for tasks.

On Cloud Run startup, this auto-provisions Pub/Sub topics and subscriptions
for all registered tasks.
"""

import logging
import os

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class TasksConfig(AppConfig):
    """App configuration for background tasks."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "gyrinx.tasks"
    verbose_name = "Background Tasks"

    def ready(self):
        """
        Initialize task infrastructure.

        - Registers signal handlers for TaskExecution lifecycle management
        - Auto-provisions Pub/Sub topics/subscriptions in Cloud Run
        """
        # Import signal handlers to register them (works with any backend)
        from gyrinx.tasks import signals  # noqa: F401

        # Only provision Pub/Sub in Cloud Run environment
        if not os.getenv("K_SERVICE"):
            logger.debug("Not in Cloud Run, skipping task provisioning")
            return

        # Don't provision during management commands
        import sys

        if len(sys.argv) > 1 and sys.argv[1] in ("migrate", "makemigrations", "test"):
            logger.debug(f"Skipping provisioning during {sys.argv[1]}")
            return

        try:
            from gyrinx.tasks.provisioning import provision_task_infrastructure

            provision_task_infrastructure()
        except Exception as e:
            # Log but don't crash the app - topics might already exist
            logger.error(f"Failed to provision task infrastructure: {e}", exc_info=True)
