from django.apps import AppConfig


class N26Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    #: Pinned for the same reason as library's — see LibraryConfig.
    name = "n26.core"
    label = "n26"
    #: The edition prefix keeps the admin index legible: two editions'
    #: apps interleave there, and "Core" next to "Content" says nothing
    #: about which game a row belongs to. Display only — the label above
    #: is the contract.
    verbose_name = "N26 · Core"

    def ready(self):
        from n26 import analytics  # noqa: F401  — claims this edition's event nouns
        from n26.core import checks  # noqa: F401  — registers startup checks
