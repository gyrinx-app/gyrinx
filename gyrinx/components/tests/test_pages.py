"""Smoke tests for registered page components."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from gyrinx.components.registry import coerce_page, resolve_page


@pytest.mark.django_db
def test_converted_page_renders_through_view(
    client, user, make_list, make_list_fighter
):
    """End-to-end: a real view render() dispatches to the component backend and
    returns a full HTML page (proves zero-view-change integration)."""
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    client.force_login(user)

    response = client.get(f"/list/{lst.id}/fighter/{fighter.id}/delete")
    assert response.status_code == 200
    body = response.content.decode()
    assert body.startswith("<!DOCTYPE html>")
    assert f"Delete: {fighter.fully_qualified_name}" in body
    assert "navbar" in body  # full shell rendered by the component Base layout
    assert 'class="btn btn-danger"' in body
    # response.context / response.templates work (test client instrumentation),
    # so existing view tests that assert on them keep passing after conversion.
    assert response.context["fighter"] == fighter
    assert response.context["list"] == lst
    assert "core/list_fighter_delete.html" in {t.name for t in response.templates}


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
