"""Development template cache configuration for django-cotton.

Cotton installs its loader chain during ready(), after settings are loaded.
The development AppConfig adjusts that chain after Cotton initialisation.
With CACHE_TEMPLATES=False, remove cached loaders while retaining their order.

The dev server normally keeps cached loaders. TemplateDirectoryWatch checks
directory modification times to invalidate them when files are added, removed
or renamed, including files unknown to Django's template autoreloader.
Production and tests retain the standard cached loader.
"""

import os
from contextlib import suppress

from django.core.exceptions import ImproperlyConfigured
from django_cotton.apps import LoaderAppConfig

CACHED_LOADER = "django.template.loaders.cached.Loader"
COTTON_LOADER = "django_cotton.cotton_loader.Loader"


def uncached_loaders(loaders):
    """Unwrap cached.Loader entries recursively and preserve other loaders.

    Only cached.Loader has the supported nested-loader configuration. Raise
    ImproperlyConfigured if that configuration is malformed.
    """
    unwrapped = []
    for loader in loaders:
        if loader == CACHED_LOADER:
            raise ImproperlyConfigured(
                f"{CACHED_LOADER} appears in the template loader chain with no "
                "wrapped loaders, so there is nothing to unwrap."
            )
        if isinstance(loader, (list, tuple)) and loader and loader[0] == CACHED_LOADER:
            if len(loader) != 2 or not isinstance(loader[1], (list, tuple)):
                raise ImproperlyConfigured(
                    f"Expected {CACHED_LOADER} to be configured as a (name, loaders) "
                    f"pair, got {loader!r}."
                )
            unwrapped.extend(uncached_loaders(loader[1]))
        else:
            unwrapped.append(loader)
    return unwrapped


def unwrap_cached_template_loader():
    """Remove cached loaders from configured template engines in place.

    Require Cotton's loader first after unwrapping; otherwise fail at startup
    because component resolution depends on that order.
    """
    from django.conf import settings

    for template_config in settings.TEMPLATES:
        options = template_config.get("OPTIONS") or {}
        loaders = options.get("loaders")
        if not loaders:
            continue

        unwrapped = uncached_loaders(loaders)
        if unwrapped == list(loaders):
            continue

        if unwrapped[0] != COTTON_LOADER:
            raise ImproperlyConfigured(
                "Unwrapping the cached template loader left a chain that does not "
                f"start with {COTTON_LOADER}: {unwrapped!r}. django-cotton's "
                "autoconfig has changed shape — see gyrinx/cotton_dev.py."
            )

        options["loaders"] = unwrapped

    reset_engines()


class TemplateDirectoryWatch:
    """Resets the template loaders when a file is added to, or leaves, a template directory.

    Connected to ``request_started``. Checking costs one ``stat`` per directory
    under the template roots, a few hundred in this project, well under a
    millisecond. Edits to existing files are left to Django's own template
    autoreload: they do not change a directory's modification time.
    """

    def __init__(self, roots=None):
        self.roots = roots
        self.mtimes = None

    def directories(self):
        if self.roots is not None:
            return self.roots
        from django.template.autoreload import get_template_directories

        return get_template_directories()

    def snapshot(self):
        """Each directory's modification time, or None for a root that is missing."""
        mtimes = {}
        for root in self.directories():
            # A missing root is recorded too, so that creating it counts as a change.
            mtimes[os.fspath(root)] = None
            for path, _subdirectories, _files in os.walk(root):
                with suppress(OSError):
                    mtimes[path] = os.stat(path).st_mtime_ns
        return mtimes

    def changed(self):
        for path, mtime in self.mtimes.items():
            try:
                current = os.stat(path).st_mtime_ns
            except OSError:
                current = None
            if current != mtime:
                return True
        return False

    def __call__(self, **kwargs):
        if self.mtimes is None:
            self.mtimes = self.snapshot()
        elif self.changed():
            from django.template.autoreload import reset_loaders

            reset_loaders()
            self.mtimes = self.snapshot()


def reset_engines():
    """Make the template engines rebuild from the current ``settings.TEMPLATES``."""
    import django.template

    # The engine handler caches settings.TEMPLATES the first time it is read;
    # drop that so the new chain is the one the engines get built from. This
    # mirrors what cotton's own wrap_loaders() does after rewriting the chain.
    with suppress(AttributeError):
        del django.template.engines.templates
    django.template.engines._engines = {}


class DevCottonConfig(LoaderAppConfig):
    """django-cotton's autoconfig, with the cached loader adjusted for editing."""

    template_directory_watch = TemplateDirectoryWatch()

    def ready(self):
        from django.conf import settings
        from django.core.signals import request_started

        super().ready()
        # Default to leaving the caching as cotton built it: this only changes it
        # where settings have explicitly asked.
        if not getattr(settings, "CACHE_TEMPLATES", True):
            unwrap_cached_template_loader()
        elif getattr(settings, "WATCH_TEMPLATE_DIRECTORIES", False):
            request_started.connect(
                self.template_directory_watch,
                dispatch_uid="gyrinx.cotton_dev.template_directory_watch",
            )
