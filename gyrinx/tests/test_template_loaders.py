"""Development template caching, invalidation and Cotton loader ordering.

Probe development settings in a subprocess because pytest retains its own
cached-loader configuration.
"""

import json
import os
import subprocess  # noqa: S404
import sys
from pathlib import Path

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.template import TemplateDoesNotExist, engines
from django.template.autoreload import get_template_directories, template_changed
from django.template.loader import get_template
from django.test import override_settings

from gyrinx.cotton_dev import (
    CACHED_LOADER,
    COTTON_LOADER,
    TemplateDirectoryWatch,
    uncached_loaders,
    unwrap_cached_template_loader,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

FILESYSTEM_LOADER = "django.template.loaders.filesystem.Loader"
APP_DIRECTORIES_LOADER = "django.template.loaders.app_directories.Loader"

# A representative cached Cotton loader chain for unwrapping tests.
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
        "  'watch': settings.WATCH_TEMPLATE_DIRECTORIES,"
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

    probed = probe_dev_settings(GYRINX_CACHE_TEMPLATES="")

    assert probed["cache_templates"] is True
    assert probed["watch"] is True
    assert flatten(probed["engine_loaders"])[:2] == [CACHED_LOADER, COTTON_LOADER]


def test_the_dev_server_can_read_templates_fresh():

    probed = probe_dev_settings(GYRINX_CACHE_TEMPLATES="False")

    assert probed["cache_templates"] is False
    assert CACHED_LOADER not in flatten(probed["settings_loaders"])
    assert CACHED_LOADER not in flatten(probed["engine_loaders"])
    # Keep Cotton's loader first so component tags compile.
    assert probed["engine_loaders"][0] == COTTON_LOADER
    assert probed["engine_loaders"].index(FILESYSTEM_LOADER) < probed[
        "engine_loaders"
    ].index(APP_DIRECTORIES_LOADER)


@pytest.mark.parametrize(
    "template_name",
    [
        "core/list.html",
        "cotton/ui/button.html",
    ],
)
def test_editing_a_template_resets_the_cached_loader(template_name):
    """Reset loaded templates through Django's template_changed handler."""
    assert flatten(engines["django"].engine.loaders)[0] == CACHED_LOADER

    before = get_template(template_name).template
    path = Path(before.origin.name)

    assert any(directory in path.parents for directory in get_template_directories())
    assert get_template(template_name).template is before

    assert template_changed(sender=None, file_path=path) is True
    assert get_template(template_name).template is not before


@pytest.fixture
def two_template_dirs(tmp_path):
    """A cached engine reading a higher- then a lower-priority directory."""
    high, low = tmp_path / "high", tmp_path / "low"
    high.mkdir()
    low.mkdir()
    config = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [str(high), str(low)],
            "OPTIONS": {"loaders": [(CACHED_LOADER, [FILESYSTEM_LOADER])]},
        }
    ]
    with override_settings(TEMPLATES=config):
        yield high, low, TemplateDirectoryWatch(roots=[high, low])


def render(name):
    return get_template(name).render({})


def test_a_new_override_shows_once_its_directory_changes(two_template_dirs):

    high, low, watch = two_template_dirs
    (low / "page.html").write_text("from low")
    watch()
    assert render("page.html") == "from low"

    (high / "page.html").write_text("from high")
    # The cached match stays stale until the directory watcher resets loaders.
    assert render("page.html") == "from low"

    watch()
    assert render("page.html") == "from high"


def test_a_template_created_after_a_miss_is_found(two_template_dirs):
    high, _low, watch = two_template_dirs
    watch()
    with pytest.raises(TemplateDoesNotExist):
        render("new.html")

    (high / "new.html").write_text("made after the miss")
    watch()

    assert render("new.html") == "made after the miss"


def test_a_template_root_created_later_is_noticed(tmp_path):

    missing = tmp_path / "later"
    watch = TemplateDirectoryWatch(roots=[missing])
    watch()
    assert not watch.changed()

    missing.mkdir()
    (missing / "new.html").write_text("made later")

    assert watch.changed()


def test_an_unchanged_directory_keeps_the_cache(two_template_dirs):
    _high, low, watch = two_template_dirs
    (low / "page.html").write_text("cached")
    watch()
    before = get_template("page.html").template

    watch()

    assert get_template("page.html").template is before


def test_cotton_is_still_installed_under_its_own_name():

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

    with pytest.raises(ImproperlyConfigured):
        uncached_loaders([(CACHED_LOADER, "not-a-list")])

    with pytest.raises(ImproperlyConfigured):
        uncached_loaders([CACHED_LOADER])


def test_unwrapping_a_chain_without_cotton_fails_loudly():

    with override_settings(
        TEMPLATES=engine_config([(CACHED_LOADER, [FILESYSTEM_LOADER])])
    ):
        with pytest.raises(ImproperlyConfigured, match=COTTON_LOADER):
            unwrap_cached_template_loader()
