"""
Development-only template loading: cotton's loader chain, without the caching.

django-cotton's autoconfig (``django_cotton.apps.LoaderAppConfig``) rewrites
``TEMPLATES[0]["OPTIONS"]["loaders"]`` from ``ready()``: it pops ``APP_DIRS`` and
substitutes its own chain, wrapped in Django's ``cached.Loader``. Django only
leaves the cached loader out under ``DEBUG`` when it builds the chain itself from
``APP_DIRS``, so cotton's substitution puts it back in development — and a
compiled template then lives for the life of the process. Editing a template
changes nothing until a restart, and a template-only edit doesn't touch a ``.py``
file, so the autoreloader never fires either.

Unwrapping the chain from ``settings_dev`` doesn't work: the autoconfig runs
later, when the app registry is populated, and overwrites whatever settings
declared. So development swaps the ``django_cotton`` entry in ``INSTALLED_APPS``
for the subclass below, which lets the autoconfig build its chain and then takes
the cached loader out of it. The chain stays cotton's own — nothing here has its
own opinion about which loaders belong in it, so a future cotton version that
changes the chain is followed rather than silently contradicted.

Whether to unwrap is the ``CACHE_TEMPLATES`` setting's call. Production keeps the
cached loader; so does the test suite, where it is a straight win.
"""

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
    import django.template
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

    # The engine handler caches settings.TEMPLATES the first time it is read;
    # drop that so the new chain is the one the engines get built from. This
    # mirrors what cotton's own wrap_loaders() does after rewriting the chain.
    with suppress(AttributeError):
        del django.template.engines.templates
    django.template.engines._engines = {}


class UncachedCottonConfig(LoaderAppConfig):
    """django-cotton's autoconfig, with the cached loader taken back out."""

    def ready(self):
        from django.conf import settings

        super().ready()
        # Default to leaving the caching in place: this only ever removes it
        # where something has explicitly asked for templates to be read fresh.
        if not getattr(settings, "CACHE_TEMPLATES", True):
            unwrap_cached_template_loader()
