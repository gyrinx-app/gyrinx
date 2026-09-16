from django.apps import AppConfig
from django.db.models.signals import post_migrate


class SiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gyrinx.site"
    label = "gyrinxsite"

    def ready(self):
        from gyrinx.site.write_pause import ensure_registered_scopes

        post_migrate.connect(
            ensure_registered_scopes,
            sender=self,
            dispatch_uid="gyrinx.site.ensure_registered_write_scopes",
        )
