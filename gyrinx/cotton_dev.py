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
template autoreload (``django/template/autoreload.py``) about every edit under a
template directory, and that resets the loaders. A file that did not exist when
the server started is the exception: the autoreloader ignores new files. The
cached loader also remembers templates it could not find, so a component written
into a page before its file existed would stay missing until a restart.
Development therefore swaps in ``CachedLoader`` below, which caches only the
templates it finds. That is the ``CACHE_MISSING_TEMPLATES`` setting's call.

``CACHE_TEMPLATES`` set to false takes the cached loader out altogether, for a
process with no autoreloader. Production and the test suite keep Django's own
cached loader.
"""

from contextlib import suppress

from django.core.exceptions import ImproperlyConfigured
from django.template import TemplateDoesNotExist
from django.template.loaders import cached
from django_cotton.apps import LoaderAppConfig

CACHED_LOADER = "django.template.loaders.cached.Loader"
DEV_CACHED_LOADER = "gyrinx.cotton_dev.CachedLoader"
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


class CachedLoader(cached.Loader):
    """Django's cached loader, minus the memory of templates it could not find."""

    def get_template(self, template_name, skip=None):
        try:
            return super().get_template(template_name, skip)
        except TemplateDoesNotExist:
            self.get_template_cache.pop(self.cache_key(template_name, skip), None)
            raise


def stop_caching_missing_templates():
    """Swap ``CachedLoader`` in for the cached loader of every engine, in place."""
    from django.conf import settings

    for template_config in settings.TEMPLATES:
        options = template_config.get("OPTIONS") or {}
        options["loaders"] = [
            (DEV_CACHED_LOADER, *loader[1:])
            if isinstance(loader, (list, tuple))
            and loader
            and loader[0] == CACHED_LOADER
            else loader
            for loader in options.get("loaders") or []
        ]

    reset_engines()


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

    def ready(self):
        from django.conf import settings

        super().ready()
        # Default to leaving the caching as cotton built it: this only changes it
        # where settings have explicitly asked.
        if not getattr(settings, "CACHE_TEMPLATES", True):
            unwrap_cached_template_loader()
        elif not getattr(settings, "CACHE_MISSING_TEMPLATES", True):
            stop_caching_missing_templates()
