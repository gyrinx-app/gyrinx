from django.apps import AppConfig


class PagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gyrinx.pages"

    def ready(self):
        # Import signals to ensure they are connected
        from . import signals  # noqa: F401
