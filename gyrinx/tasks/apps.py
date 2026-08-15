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
        """
        Register signal handlers for TaskExecution lifecycle management.

        Pub/Sub provisioning deliberately does **not** happen here. `ready()` runs
        in every Django process — every management command and every gunicorn
        worker — and provisioning is a serial run of blocking Pub/Sub admin calls.
        On Cloud Run that meant four runs per container (collectstatic,
        ensuresuperuser, and once per worker), ~120s of a ~160s cold start, all of
        it re-creating resources that already existed. Worse, the workers ran it
        *after* gunicorn had bound the port, so Cloud Run's startup probe passed
        and real requests were routed into processes still blocked in `ready()`.

        Provisioning is now a background step in `docker/entrypoint.sh`
        (`manage provision_tasks`), off the request path entirely.
        """
        # Import signal handlers to register them (works with any backend)
        from gyrinx.tasks import signals  # noqa: F401  # isort: skip

        # Import the system check module so its @register() runs — enforces that
        # every @task is in the registry, in every environment (#1947).
        from gyrinx.tasks import checks  # noqa: F401  # isort: skip
