"""Golden-equivalence test: list_archive component matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_archive_matches_legacy(user, make_list):
    lst = make_list("Iron Skulls", owner=user)
    request = _request(user)
    context = {
        "list": lst,
        "is_in_active_campaign": False,
        "active_campaigns": [],
    }
    assert_equivalent("core/list_archive.html", context, request)
