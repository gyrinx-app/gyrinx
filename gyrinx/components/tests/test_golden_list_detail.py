"""Golden-equivalence test for the gang detail page (``core/list.html``)."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_detail_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    # DetailView stamps each fighter with the pack-name label (empty here — the
    # gang has no subscribed packs) before the fighter card reads it.
    fighter.from_pack_name = ""

    request = _request(user, path=f"/list/{lst.id}/")

    # Mirror ListDetailView.get_context_data for a list-building gang the viewer
    # owns (non-campaign, so no recent_actions/campaign_resources/held_assets).
    context = {
        "list": lst,
        "has_stash_fighter": False,
        "fighters_with_groups": [fighter],
        "fighters_minimal": [{"id": fighter.id, "name": fighter.name}],
        "pending_invitations_count": 0,
        "can_impersonate_list_owner": False,
        "subscribed_packs": [],
        "suggested_campaign_packs_count": 0,
        "pack_content_map": {},
        "star_count": 0,
        "is_pinned": False,
        "is_starred": False,
        "notification_banners": [],
        "is_campaign_arbitrator": False,
    }

    assert_equivalent("core/list.html", context, request)
