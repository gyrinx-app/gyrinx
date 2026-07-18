"""Tests for the component template backend and its coexistence with Django templates."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.template import TemplateDoesNotExist, engines
from django.template.loader import render_to_string
from django.test import RequestFactory

from gyrinx.components import div
from gyrinx.components.layout import Page
from gyrinx.components import registry


@pytest.fixture
def components_engine():
    return _get_components_engine()


def _get_components_engine():
    for engine in engines.all():
        if engine.__class__.__name__ == "Components":
            return engine
    raise AssertionError("Components backend is not configured")


@pytest.fixture
def register_temp_page():
    """Register a page component for the duration of a test, then remove it."""
    added: list[str] = []

    def _register(name, fn):
        registry._REGISTRY[name] = fn
        fn.template_name = name
        added.append(name)

    yield _register
    for name in added:
        registry._REGISTRY.pop(name, None)


def test_backend_is_first():
    engine = engines.all()[0]
    assert engine.__class__.__name__ == "Components"


def test_backend_raises_for_unregistered_name():
    engine = _get_components_engine()
    with pytest.raises(TemplateDoesNotExist):
        engine.get_template("core/definitely_not_a_component.html")


def test_unknown_name_falls_through_to_django_templates():
    # A real Django template that is NOT a component still loads via the
    # DjangoTemplates backend (proves fall-through / coexistence).
    from django.template.loader import get_template

    tmpl = get_template("core/includes/back.html")
    assert tmpl.render({"url": "/x", "text": "Back"})


@pytest.mark.django_db
def test_registered_component_renders_via_loader(register_temp_page):
    def my_page(context):
        return Page(title="Smoke", content=div(id="smoke")["it works"])

    register_temp_page("core/__test_smoke__.html", my_page)

    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    html = render_to_string("core/__test_smoke__.html", {}, request=request)

    assert "<!DOCTYPE html>" in html
    assert "<title>Smoke | Gyrinx</title>" in html
    assert '<div id="smoke">it works</div>' in html


@pytest.mark.django_db
def test_component_receives_context_processor_values(register_temp_page):
    captured = {}

    def my_page(context):
        captured.update(context)
        return Page(title="Ctx", content=div["x"])

    register_temp_page("core/__test_ctx__.html", my_page)

    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    render_to_string("core/__test_ctx__.html", {"extra": 1}, request=request)

    # View-supplied key preserved, and context processors ran (request/user/etc.)
    assert captured["extra"] == 1
    assert captured["request"] is request
    assert "user" in captured
    # gyrinx_debug context processor injects this key
    assert "gyrinx_debug" in captured


@pytest.mark.django_db
def test_view_context_beats_context_processor(register_temp_page, django_user_model):
    """RequestContext precedence: an explicit view value wins over a context
    processor of the same name. A page showing someone else's profile passes its
    own ``user``; letting the auth processor overwrite it with ``request.user``
    would render the wrong person — and silently diverge from the legacy template."""
    captured = {}

    def my_page(context):
        captured.update(context)
        return Page(title="Ctx", content=div["x"])

    register_temp_page("core/__test_ctx_precedence__.html", my_page)

    viewer = django_user_model.objects.create_user(username="viewer", password="pw")
    subject = django_user_model.objects.create_user(username="subject", password="pw")
    request = RequestFactory().get("/")
    request.user = viewer

    render_to_string(
        "core/__test_ctx_precedence__.html", {"user": subject}, request=request
    )

    assert captured["user"] == subject
