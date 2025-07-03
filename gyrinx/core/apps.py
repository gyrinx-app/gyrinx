from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gyrinx.core"

    def ready(self):
        """Import signal handlers when the app is ready."""
        import gyrinx.core.signals  # noqa: F401
