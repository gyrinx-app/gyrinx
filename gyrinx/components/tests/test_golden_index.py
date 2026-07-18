"""Golden-equivalence test for the home / dashboard page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_index_matches_legacy(user, make_list):
    # Replicates the authenticated GET branch of ``views.home.index`` with a
    # single list-building List and no gangs, campaigns, pins or featured packs.
    lst = make_list("Iron Skulls", owner=user)
    request = _request(user)
    context = {
        "lists": [lst],
        "campaign_gangs": [],
        "campaigns": [],
        "houses": [],
        "has_any_lists": True,
        "search_query": None,
        "search_gangs_query": None,
        "search_campaigns_query": None,
        "featured_packs": [],
        "pinned_lists": [],
        "pinned_gangs": [],
        "pinned_campaigns": [],
    }
    assert_equivalent("core/index.html", context, request)
