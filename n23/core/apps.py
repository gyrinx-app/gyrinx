from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "n23.core"
    # Pinned, not left to the default. The label is what every table name,
    # migration record, content type and "core.ListFighter" reference is keyed
    # on, so it is the contract that let this app move packages without a single
    # database change. It also stops resolving to the same default as a future
    # n26.core. Changing it means renaming tables — don't.
    label = "core"
    # Edition-prefixed so the admin index says which game an app belongs
    # to now that two editions' apps interleave there. Display only — the
    # label above is the contract.
    verbose_name = "N23 · Core"

    def ready(self):
        """Import signal handlers when the app is ready."""
        import n23.core.checks  # noqa: F401
        import n23.core.signals  # noqa: F401
