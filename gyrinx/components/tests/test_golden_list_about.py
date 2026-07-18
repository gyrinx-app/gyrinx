"""Golden-equivalence test: list About (gang lore) display page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_about_matches_legacy(user, make_list):
    lst = make_list("Iron Skulls", owner=user)
    request = _request(user)
    # ListAboutDetailView is a DetailView with context_object_name="list",
    # so the GET branch passes only the List object as ``list``.
    context = {"list": lst}
    assert_equivalent("core/list_about.html", context, request)
