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
        # runserver's autoreloader runs Django twice: a parent that starts the
        # child again whenever it exits with code 3, and a child, marked by
        # RUN_MAIN, that serves and watches the files. Only the child.
        if os.environ.get("RUN_MAIN") != "true" and "--noreload" not in sys.argv:
            return
        from gyrinx.devserver import guard

        guard.start(
            memory_limit_mb=settings.DEV_SERVER_MEMORY_LIMIT_MB,
            idle_minutes=settings.DEV_SERVER_IDLE_MINUTES,
        )
