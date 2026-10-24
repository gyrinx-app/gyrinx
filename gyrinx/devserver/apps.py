import os
import sys

from django.apps import AppConfig
from django.conf import settings


class DevServerConfig(AppConfig):
    """Development-only: starts the guard and the imported-source watch."""

    name = "gyrinx.devserver"
    label = "gyrinx_devserver"

    def ready(self):
        if not getattr(settings, "DEV_SERVER_GUARD", False):
            return
        # runserver's autoreloader runs Django twice: a parent that starts the
        # child again whenever it exits with code 3, and a child, marked by
        # RUN_MAIN, that serves. The guard also runs for --noreload, which has
        # no parent to restart it. The source watch needs that parent.
        serving = os.environ.get("RUN_MAIN") == "true"
        if not serving and "--noreload" not in sys.argv:
            return
        from gyrinx.devserver import guard

        guard.start(
            memory_limit_mb=settings.DEV_SERVER_MEMORY_LIMIT_MB,
            idle_minutes=settings.DEV_SERVER_IDLE_MINUTES,
        )
        if serving:
            from gyrinx.devserver.python_watch import install

            install(settings.BASE_DIR)
