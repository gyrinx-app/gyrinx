"""The shared-context Templates panel shows what the toolbar's own panel shows."""

import pytest
from debug_toolbar.panels.templates.panel import TemplatesPanel
from debug_toolbar.store import get_store
from debug_toolbar.toolbar import DebugToolbar, StoredDebugToolbar
from django.http import HttpResponse
from django.template import Context, Engine
from django.test import RequestFactory
from django.urls import include, path

from gyrinx.toolbar_panels import SharedContextTemplatesPanel

TEMPLATES = {
    "page.html": (
        "{% for row in rows %}{% include 'row.html' %}{% endfor %}"
        "{% include 'row.html' with extra='x' %}"
    ),
    "row.html": "{{ row }}{{ extra }}",
}


class ToolbarURLs:
    """The toolbar's own URLs, which the panel's HTML links to."""

    urlpatterns = [path("__debug__/", include("debug_toolbar.urls"))]


@pytest.fixture(autouse=True)
def toolbar_urls(settings):
    settings.ROOT_URLCONF = ToolbarURLs


@pytest.fixture(autouse=True)
def fixed_signing_time(monkeypatch):
    """The panel links each template with a signed origin that carries the time.

    Two renders a second apart would otherwise differ in every link.
    """
    monkeypatch.setattr(
        "django.core.signing.TimestampSigner.timestamp", lambda self: "0"
    )


def respond(request):
    return HttpResponse()


def run_panel(panel_class):
    """Render a page through one panel, as the toolbar would, and return it."""
    request = RequestFactory().get("/")
    toolbar = DebugToolbar(request, respond)
    panel = panel_class(toolbar, respond)
    engine = Engine(loaders=[("django.template.loaders.locmem.Loader", TEMPLATES)])
    panel.enable_instrumentation()
    try:
        engine.get_template("page.html").render(
            Context({"rows": ["a", "b", "c"], "title": "A page", "notes": "—" * 50})
        )
    finally:
        panel.disable_instrumentation()
    panel.generate_stats(request, HttpResponse())
    return toolbar, panel


def test_development_uses_the_shared_context_panel():
    request = RequestFactory().get("/")
    toolbar = DebugToolbar(request, respond)
    panel = toolbar.get_panel_by_id("TemplatesPanel")
    assert type(panel) is SharedContextTemplatesPanel
    get_store().delete(toolbar.request_id)


def test_the_panel_shows_what_the_toolbars_own_panel_shows():
    stock_toolbar, stock = run_panel(TemplatesPanel)
    toolbar, panel = run_panel(SharedContextTemplatesPanel)
    try:
        assert panel.panel_id == stock.panel_id == "TemplatesPanel"
        assert panel.title == stock.title
        assert panel.nav_subtitle == stock.nav_subtitle
        assert panel.content == stock.content
        assert "A page" in panel.content
    finally:
        get_store().delete(stock_toolbar.request_id)
        get_store().delete(toolbar.request_id)


def test_each_context_layer_is_kept_once():
    toolbar, panel = run_panel(SharedContextTemplatesPanel)
    try:
        stats = panel.get_stats()
        layers = stats["context_layers"]
        assert len(layers) == len(set(layers))
        templates = stats["templates"]
        assert len(templates) == 5
        assert all("context" not in info for info in templates)
        # Every include sees the page's own context layer.
        page_layer = next(i for i, text in enumerate(layers) if "A page" in text)
        assert all(page_layer in info["context_layers"] for info in templates)
    finally:
        get_store().delete(toolbar.request_id)


def test_a_past_request_shows_what_the_toolbars_own_panel_shows():
    stock_toolbar, stock = run_panel(TemplatesPanel)
    toolbar, _ = run_panel(SharedContextTemplatesPanel)
    try:
        stored = StoredDebugToolbar.from_store(
            toolbar.request_id, panel_id="TemplatesPanel"
        )
        assert stored.get_panel_by_id("TemplatesPanel").content == stock.content
    finally:
        get_store().delete(stock_toolbar.request_id)
        get_store().delete(toolbar.request_id)


def test_without_template_context_the_panel_lists_templates_only():
    from debug_toolbar import settings as dt_settings

    config = dt_settings.get_config()
    shown = config["SHOW_TEMPLATE_CONTEXT"]
    config["SHOW_TEMPLATE_CONTEXT"] = False
    try:
        stock_toolbar, stock = run_panel(TemplatesPanel)
        toolbar, panel = run_panel(SharedContextTemplatesPanel)
    finally:
        config["SHOW_TEMPLATE_CONTEXT"] = shown
    try:
        assert "context_layers" not in panel.get_stats()
        assert panel.content == stock.content
    finally:
        get_store().delete(stock_toolbar.request_id)
        get_store().delete(toolbar.request_id)
