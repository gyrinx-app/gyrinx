"""Tests for the full-document layout components (Foundation / Base / SimplePage)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from gyrinx.components import div, p
from gyrinx.components.layout import Page, render_page


def _context(path="/", user=None):
    request = RequestFactory().get(path)
    request.user = user or AnonymousUser()
    return {
        "request": request,
        "user": request.user,
        "messages": [],
        "debug": False,
    }


@pytest.mark.django_db
def test_base_layout_full_document():
    ctx = _context()
    page = Page(title="Home", content=div(id="marker")["Body content"])
    html = render_page(page, ctx)

    assert html.startswith("<!DOCTYPE html>")
    assert '<html lang="en"' in html
    assert "<title>Home | Gyrinx</title>" in html
    # Navbar + brand
    assert 'class="navbar navbar-expand-lg bg-dark"' in html
    assert ">Gyrinx</span>" in html
    # Anonymous users get Sign In / Sign Up
    assert "Sign In" in html
    assert "Sign Up" in html
    # Content is wrapped in #content container
    assert '<div id="content" class="container my-3 my-md-5">' in html
    assert '<div id="marker">Body content</div>' in html
    # Footer
    assert 'class="bd-footer' in html
    # Scripts
    assert "bootstrap.bundle.min.js" in html
    assert "core/js/index.js" in html


@pytest.mark.django_db
def test_base_layout_authenticated(django_user_model):
    user = django_user_model.objects.create_user(username="alice", password="pw")
    ctx = _context(user=user)
    page = Page(title="Dash", content=p["hi"])
    html = render_page(page, ctx)

    # Authenticated users get the account button + dice + notifications
    assert "alice" in html
    assert "bi-inbox" in html  # notification button
    assert "bi-dice-6" in html
    assert "Sign In" not in html


@pytest.mark.django_db
def test_foundation_layout_only():
    ctx = _context()
    page = Page(title="Bare", content=div["x"], layout="foundation")
    html = render_page(page, ctx)
    assert html.startswith("<!DOCTYPE html>")
    assert "<title>Bare | Gyrinx</title>" in html
    # No navbar/footer in the bare foundation layout
    assert "navbar" not in html
    assert "bd-footer" not in html
    assert "<div>x</div>" in html


@pytest.mark.django_db
def test_simple_page_layout():
    ctx = _context()
    page = Page(
        title="About", content=div["body"], description="A subtitle", layout="page"
    )
    html = render_page(page, ctx)
    assert '<h1 class="h3 mb-0">About</h1>' in html
    assert "A subtitle" in html
    assert "navbar" in html  # page layout still wraps in base


@pytest.mark.django_db
def test_messages_rendered():
    from django.contrib.messages.storage.base import Message
    from django.contrib.messages import constants

    ctx = _context()
    ctx["messages"] = [
        Message(constants.SUCCESS, "Saved!"),
        Message(constants.ERROR, "Broke!"),
    ]
    page = Page(title="X", content=div["y"])
    html = render_page(page, ctx)
    assert "alert-success" in html
    assert "Saved!" in html
    assert "alert-danger" in html
    assert "Broke!" in html


@pytest.mark.django_db
def test_content_is_escaped_but_components_are_not():
    ctx = _context()
    page = Page(title="X", content=div["<b>not bold</b>"])
    html = render_page(page, ctx)
    assert "&lt;b&gt;not bold&lt;/b&gt;" in html
