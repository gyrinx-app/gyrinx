import os
import sys

from django.apps import AppConfig
from django.conf import settings


class DevServerConfig(AppConfig):
    """Development-only: starts ``gyrinx/devserver/guard.py`` under runserver."""

    name = "gyrinx.devserver"
    label = "gyrinx_devserver"

    def ready(self):
        if not getattr(settings, "DEV_SERVER_GUARD", False):
            return
        # Start the guard in the serving process, including --noreload.
        # Skip the autoreloader parent identified by the absence of RUN_MAIN.
        if os.environ.get("RUN_MAIN") != "true" and "--noreload" not in sys.argv:
            return
        from gyrinx.devserver import guard

        guard.start(
            memory_limit_mb=settings.DEV_SERVER_MEMORY_LIMIT_MB,
            idle_minutes=settings.DEV_SERVER_IDLE_MINUTES,
        )
