"""
Development-only template loading: cotton's loader chain, adjusted for editing.

django-cotton's autoconfig (``django_cotton.apps.LoaderAppConfig``) rewrites
``TEMPLATES[0]["OPTIONS"]["loaders"]`` from ``ready()``: it pops ``APP_DIRS`` and
substitutes its own chain, wrapped in Django's ``cached.Loader``. Rewriting that
chain from ``settings_dev`` doesn't work: the autoconfig runs later, when the app
registry is populated, and overwrites whatever settings declared. So development
swaps the ``django_cotton`` entry in ``INSTALLED_APPS`` for the subclass below,
which lets the autoconfig build its chain and then adjusts it. The chain stays
cotton's own — nothing here has its own opinion about which loaders belong in it,
so a future cotton version that changes the chain is followed rather than
silently contradicted.

The dev server keeps the cached loader. runserver's autoreloader tells Django's
template autoreload (``django/template/autoreload.py``) about every edit to a file
under a template directory, and that resets the loaders. It ignores files that
did not exist when it started, though, so a new template would never reach the
cache: not a component written into a page before its file existed, and not an
override of a template that had already loaded from a lower-priority directory.
``TemplateDirectoryWatch`` below covers that. Adding, removing or renaming a file
changes its directory's modification time, so before each request it checks
those times and resets the loaders when one has moved. That is the
``WATCH_TEMPLATE_DIRECTORIES`` setting's call.

``CACHE_TEMPLATES`` set to false takes the cached loader out altogether, for a
process with no autoreloader. Production and the test suite keep Django's own
cached loader.
"""

import os
from contextlib import suppress

from django.core.exceptions import ImproperlyConfigured
from django_cotton.apps import LoaderAppConfig

CACHED_LOADER = "django.template.loaders.cached.Loader"
COTTON_LOADER = "django_cotton.cotton_loader.Loader"


def uncached_loaders(loaders):
    """
    Return ``loaders`` with every cached loader replaced by the loaders it wraps.

    Anything that isn't a cached loader is passed through untouched, including
    other wrapping loaders — only ``cached.Loader`` takes a plain list of loaders
    as its argument, so it's the only one it is safe to splice.
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
    """
    Take the cached loader out of every configured template engine, in place.

    Engines that don't have one are left exactly as they are. An engine that does
    must come out of the unwrap with cotton's loader first, or the shape cotton
    builds has changed and this module needs revisiting — better a hard failure at
    startup than a chain that quietly resolves components the wrong way.
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
        mtimes = {}
        for root in self.directories():
            for path, _subdirectories, _files in os.walk(root):
                with suppress(OSError):
                    mtimes[path] = os.stat(path).st_mtime_ns
        return mtimes

    def changed(self):
        for path, mtime in self.mtimes.items():
            try:
                if os.stat(path).st_mtime_ns != mtime:
                    return True
            except OSError:
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
