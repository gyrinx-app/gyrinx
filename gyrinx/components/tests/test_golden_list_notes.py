"""Golden-equivalence test for the gang notes display page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_notes_matches_legacy(user, make_list):
    lst = make_list("Iron Skulls", owner=user)
    request = _request(user)
    context = {"list": lst}
    assert_equivalent("core/list_notes.html", context, request)
