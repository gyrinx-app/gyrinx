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


@pytest.mark.django_db
def test_campaign_remove_list_matches_legacy(user, make_campaign, make_list):
    campaign = make_campaign("Underhive Wars")
    lst = make_list("Iron Skulls", owner=user)
    request = _request(user)
    context = {"campaign": campaign, "list": lst}
    assert_equivalent("core/campaign/campaign_remove_list.html", context, request)


@pytest.mark.django_db
def test_list_clone_matches_legacy(user, make_list):
    from gyrinx.core.forms.list import CloneListForm

    lst = make_list("Iron Skulls", owner=user)
    form = CloneListForm(list_to_clone=lst)
    request = _request(user)
    context = {"form": form, "list": lst, "error_message": None}
    assert_equivalent("core/list_clone.html", context, request)


@pytest.mark.django_db
def test_campaign_new_matches_legacy(user):
    from gyrinx.core.forms.campaign import NewCampaignForm

    form = NewCampaignForm()
    request = _request(user)
    context = {"form": form, "error_message": None}
    assert_equivalent("core/campaign/campaign_new.html", context, request)


@pytest.mark.django_db
def test_campaign_edit_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import EditCampaignForm

    campaign = make_campaign("Underhive Wars")
    form = EditCampaignForm(instance=campaign)
    request = _request(user)
    context = {"form": form, "campaign": campaign, "error_message": None}
    assert_equivalent("core/campaign/campaign_edit.html", context, request)
