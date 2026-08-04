from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "n23.core"

    def ready(self):
        """Import signal handlers when the app is ready."""
        import n23.core.checks  # noqa: F401
        import n23.core.signals  # noqa: F401
