from django.apps import AppConfig


class N26Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    #: Pinned for the same reason as library's — see LibraryConfig.
    name = "n26.core"
    label = "n26"

    def ready(self):
        from n26.core import checks  # noqa: F401  — registers startup checks
