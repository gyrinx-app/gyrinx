"""The development template loader chain serves templates from disk.

django-cotton's autoconfig wraps the chain in Django's ``cached.Loader``, which
holds compiled templates for the life of the process — so in development a
template edit shows nothing until a restart, and since a template-only edit
touches no ``.py`` file, the autoreloader doesn't fire either. Development
substitutes ``gyrinx.cotton_dev.UncachedCottonConfig``, which lets the autoconfig
build its chain and then takes the cached loader back out.

The suite itself keeps the cached loader (``CACHE_TEMPLATES``), so the live
settings these tests run under are *not* the dev server's. The end-to-end
assertion is therefore made in a subprocess, against a real ``django.setup()``.
"""

import json
import os
import subprocess  # noqa: S404
import sys
from pathlib import Path

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from gyrinx.cotton_dev import (
    CACHED_LOADER,
    COTTON_LOADER,
    uncached_loaders,
    unwrap_cached_template_loader,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

FILESYSTEM_LOADER = "django.template.loaders.filesystem.Loader"
APP_DIRECTORIES_LOADER = "django.template.loaders.app_directories.Loader"

# The shape cotton's autoconfig produces, as of 2.7.2. The subprocess test below
# is what catches this going out of date; these unit tests only need a chain of
# the right shape to exercise the unwrap.
COTTON_CACHED_CHAIN = [
    (CACHED_LOADER, [COTTON_LOADER, FILESYSTEM_LOADER, APP_DIRECTORIES_LOADER])
]


def flatten(loaders):
    """Every loader name in a chain, including ones nested inside a wrapper."""
    names = []
    for loader in loaders:
        if isinstance(loader, (list, tuple)):
            names.append(loader[0])
            names.extend(flatten(loader[1] if len(loader) > 1 else []))
        else:
            names.append(loader)
    return names


def engine_config(loaders):
    return [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [],
            "OPTIONS": {"loaders": loaders},
        }
    ]


def test_the_dev_server_gets_no_cached_loader():
    """The whole point: a template edit has to reach the next request.

    Run out of process because the suite runs with CACHE_TEMPLATES on, so the
    live settings here are not the ones the dev server boots with.
    """
    probe = (
        "import django, json; django.setup();"
        "from django.conf import settings;"
        "from django.template import engines;"
        "print('PROBE' + json.dumps({"
        "  'settings_loaders': settings.TEMPLATES[0]['OPTIONS']['loaders'],"
        "  'engine_loaders': engines['django'].engine.loaders,"
        "  'cache_templates': settings.CACHE_TEMPLATES,"
        "}))"
    )
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            "DJANGO_SETTINGS_MODULE": "gyrinx.settings_dev",
            "TRACING_MODE": "off",
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("PROBE"))
    probed = json.loads(line.removeprefix("PROBE"))

    assert probed["cache_templates"] is False
    assert CACHED_LOADER not in flatten(probed["settings_loaders"])
    assert CACHED_LOADER not in flatten(probed["engine_loaders"])
    # Cotton's loader compiles the <c-…> tags, so it has to stay in front.
    assert probed["engine_loaders"][0] == COTTON_LOADER
    assert probed["engine_loaders"].index(FILESYSTEM_LOADER) < probed[
        "engine_loaders"
    ].index(APP_DIRECTORIES_LOADER)


def test_cotton_is_still_installed_under_its_own_name():
    """The swapped-in AppConfig keeps cotton installed — checks.py relies on it."""
    assert apps.is_installed("django_cotton")
    assert (
        apps.get_app_config("django_cotton").__class__.__module__ == "gyrinx.cotton_dev"
    )


def test_unwrapping_leaves_cottons_own_order_intact():
    with override_settings(TEMPLATES=engine_config(COTTON_CACHED_CHAIN)):
        unwrap_cached_template_loader()

        from django.conf import settings

        assert settings.TEMPLATES[0]["OPTIONS"]["loaders"] == [
            COTTON_LOADER,
            FILESYSTEM_LOADER,
            APP_DIRECTORIES_LOADER,
        ]


def test_uncached_loaders_splices_the_wrapped_chain():
    assert uncached_loaders(COTTON_CACHED_CHAIN) == [
        COTTON_LOADER,
        FILESYSTEM_LOADER,
        APP_DIRECTORIES_LOADER,
    ]


def test_uncached_loaders_leaves_an_uncached_chain_alone():
    chain = [COTTON_LOADER, (FILESYSTEM_LOADER, ["/somewhere"]), APP_DIRECTORIES_LOADER]

    assert uncached_loaders(chain) == chain


def test_uncached_loaders_rejects_a_cached_loader_it_cannot_unwrap():
    """A shape we don't recognise fails loudly rather than serving a broken chain."""
    with pytest.raises(ImproperlyConfigured):
        uncached_loaders([(CACHED_LOADER, "not-a-list")])

    with pytest.raises(ImproperlyConfigured):
        uncached_loaders([CACHED_LOADER])


def test_unwrapping_a_chain_without_cotton_fails_loudly():
    """If cotton's autoconfig ever changes shape, startup should say so."""
    with override_settings(
        TEMPLATES=engine_config([(CACHED_LOADER, [FILESYSTEM_LOADER])])
    ):
        with pytest.raises(ImproperlyConfigured, match=COTTON_LOADER):
            unwrap_cached_template_loader()
