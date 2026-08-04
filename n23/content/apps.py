from django.apps import AppConfig


class ContentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "n23.content"
    # Pinned deliberately — see the note in n23/core/apps.py. This label is the
    # reason the package move required no database change.
    label = "content"
