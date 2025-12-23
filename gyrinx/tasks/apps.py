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
        Auto-provision Pub/Sub infrastructure on Cloud Run startup.

        Only runs in production when K_SERVICE is set (Cloud Run environment).
        Skipped during migrations, tests, and local development.
        """
        # Only provision in Cloud Run environment
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
