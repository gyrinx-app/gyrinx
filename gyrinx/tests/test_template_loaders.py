"""How development loads templates: cached, and reset when a template changes.

django-cotton's autoconfig wraps the chain in Django's ``cached.Loader``. The dev
server keeps a cached loader, because Django's template autoreload watches every
template directory and resets the loaders when a template file changes, so an
edit still reaches the next request without a restart. Development substitutes
``gyrinx.cotton_dev.DevCottonConfig``, which swaps in a cached loader that never
remembers a missing template: the autoreloader ignores newly created files.

``GYRINX_CACHE_TEMPLATES=False`` takes the cached loader out altogether, for a
process with no autoreloader that must still see template edits.

The suite keeps Django's own cached loader, so the dev server's settings are
probed in a subprocess, against a real ``django.setup()``.
"""

import json
import os
import subprocess  # noqa: S404
import sys
from pathlib import Path

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.template import Context, Engine, TemplateDoesNotExist, engines
from django.template.autoreload import get_template_directories, template_changed
from django.template.loader import get_template
from django.test import override_settings

from gyrinx.cotton_dev import (
    CACHED_LOADER,
    COTTON_LOADER,
    DEV_CACHED_LOADER,
    CachedLoader,
    stop_caching_missing_templates,
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


def probe_dev_settings(**env):
    """The template settings ``gyrinx.settings_dev`` boots with, outside pytest."""
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
            **env,
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("PROBE"))
    return json.loads(line.removeprefix("PROBE"))


def test_the_dev_server_keeps_the_cached_loader():
    """Compiled templates survive between requests; autoreload clears them."""
    probed = probe_dev_settings(GYRINX_CACHE_TEMPLATES="")

    assert probed["cache_templates"] is True
    assert flatten(probed["engine_loaders"])[:2] == [DEV_CACHED_LOADER, COTTON_LOADER]


def test_the_dev_server_can_read_templates_fresh():
    """GYRINX_CACHE_TEMPLATES=False takes the cached loader out, cotton first."""
    probed = probe_dev_settings(GYRINX_CACHE_TEMPLATES="False")

    assert probed["cache_templates"] is False
    assert CACHED_LOADER not in flatten(probed["settings_loaders"])
    assert CACHED_LOADER not in flatten(probed["engine_loaders"])
    # Cotton's loader compiles the <c-…> tags, so it has to stay in front.
    assert probed["engine_loaders"][0] == COTTON_LOADER
    assert probed["engine_loaders"].index(FILESYSTEM_LOADER) < probed[
        "engine_loaders"
    ].index(APP_DIRECTORIES_LOADER)


@pytest.mark.parametrize(
    "template_name",
    [
        # A plain app template, and a cotton component from an app directory.
        "core/list.html",
        "cotton/ui/button.html",
    ],
)
def test_editing_a_template_resets_the_cached_loader(template_name):
    """What keeps template edits live under runserver with the cache on.

    runserver's autoreloader watches the directories this returns and sends
    file_changed for each edit. Django's template_changed handler then resets
    every loader, so the next render compiles the file again.
    """
    assert flatten(engines["django"].engine.loaders)[0] == CACHED_LOADER

    before = get_template(template_name).template
    path = Path(before.origin.name)

    assert any(directory in path.parents for directory in get_template_directories())
    assert get_template(template_name).template is before

    assert template_changed(sender=None, file_path=path) is True
    assert get_template(template_name).template is not before


def test_a_template_created_after_a_miss_is_found(tmp_path):
    """The dev loader caches what it finds, never what it could not find."""
    engine = Engine(
        dirs=[str(tmp_path)],
        loaders=[(DEV_CACHED_LOADER, [FILESYSTEM_LOADER])],
    )
    (loader,) = engine.template_loaders
    assert isinstance(loader, CachedLoader)

    with pytest.raises(TemplateDoesNotExist):
        engine.get_template("new.html")

    (tmp_path / "new.html").write_text("made after the miss")

    found = engine.get_template("new.html")
    assert found.render(Context()) == "made after the miss"
    assert engine.get_template("new.html") is found


def test_stopping_caching_misses_keeps_cottons_chain():
    with override_settings(TEMPLATES=engine_config(COTTON_CACHED_CHAIN)):
        stop_caching_missing_templates()

        from django.conf import settings

        assert settings.TEMPLATES[0]["OPTIONS"]["loaders"] == [
            (
                DEV_CACHED_LOADER,
                [COTTON_LOADER, FILESYSTEM_LOADER, APP_DIRECTORIES_LOADER],
            )
        ]


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
