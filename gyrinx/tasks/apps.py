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
        worker — and provisioning is a run of blocking Pub/Sub admin calls. On
        Cloud Run that puts four runs in each container (collectstatic,
        ensuresuperuser, and one per worker), around two minutes of a
        two-and-a-half minute cold start, all of it re-creating resources that
        already exist. The runs inside the workers are the worst of them: they
        happen after gunicorn has bound the port, so the startup probe passes and
        real requests are routed into processes still blocked in `ready()`.

        Provisioning belongs in `docker/entrypoint.sh` (`manage provision_tasks`),
        off the request path entirely.
        """
        # Import signal handlers to register them (works with any backend)
        from gyrinx.tasks import signals  # noqa: F401  # isort: skip

        # Import the system check module so its @register() runs — enforces that
        # every @task is in the registry, in every environment (#1947).
        from gyrinx.tasks import checks  # noqa: F401  # isort: skip
