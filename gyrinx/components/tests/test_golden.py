"""Golden-equivalence tests: converted pages match their legacy templates."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_delete_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "fighter_cost": fighter.cost_int(),
    }
    assert_equivalent("core/list_fighter_delete.html", context, request)


@pytest.mark.django_db
def test_list_fighter_kill_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)
    context = {"list": lst, "fighter": fighter}
    assert_equivalent("core/list_fighter_kill.html", context, request)


@pytest.mark.django_db
def test_campaign_end_matches_legacy(user, make_campaign):
    campaign = make_campaign("Underhive Wars")
    request = _request(user)
    assert_equivalent(
        "core/campaign/campaign_end.html", {"campaign": campaign}, request
    )


@pytest.mark.django_db
def test_campaign_reopen_matches_legacy(user, make_campaign):
    campaign = make_campaign("Underhive Wars")
    request = _request(user)
    assert_equivalent(
        "core/campaign/campaign_reopen.html", {"campaign": campaign}, request
    )


@pytest.mark.django_db
def test_campaign_start_matches_legacy(user, make_campaign):
    campaign = make_campaign("Underhive Wars")
    request = _request(user)
    context = {"campaign": campaign, "lists": []}
    assert_equivalent("core/campaign/campaign_start.html", context, request)


@pytest.mark.django_db
def test_campaign_archive_matches_legacy(user, make_campaign):
    campaign = make_campaign("Underhive Wars")
    request = _request(user)
    assert_equivalent(
        "core/campaign/campaign_archive.html", {"campaign": campaign}, request
    )
