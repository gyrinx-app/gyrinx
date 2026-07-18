"""Golden-equivalence test for the Lists & Gangs index page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.views.list.views import ListsListView


def _request(user, path="/lists/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_lists_matches_legacy(user, make_list):
    make_list("Iron Skulls", owner=user)
    make_list("Rust Runners", owner=user)

    request = _request(user)
    view = ListsListView()
    view.request = request
    view.kwargs = {}
    view.object_list = view.get_queryset()
    context = view.get_context_data()

    assert_equivalent("core/lists.html", context, request)
