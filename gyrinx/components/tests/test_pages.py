"""Smoke tests for registered page components."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from gyrinx.components.registry import coerce_page, resolve_page


@pytest.mark.django_db
def test_gallery_page_renders():
    from gyrinx.components.layout import render_page

    component = resolve_page("core/debug/components.html")
    assert component is not None

    request = RequestFactory().get("/_debug/components/")
    request.user = AnonymousUser()
    ctx = {"request": request, "user": request.user, "messages": [], "debug": True}
    page = coerce_page(component(ctx), ctx)
    html = render_page(page, ctx)

    assert "Component library" in html
    assert "btn btn-primary" in html
    assert "alert alert-success" in html
    assert "bi-plus-lg" in html
    # Whole document
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
