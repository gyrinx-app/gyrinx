"""Golden-equivalence test: campaign "Add Gangs" page matches its legacy template."""

from __future__ import annotations

import pytest
from django.core.paginator import Paginator
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.list import List


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_add_lists_matches_legacy(user, make_campaign, make_list):
    campaign = make_campaign("Underhive Wars")
    lst = make_list("Iron Skulls", owner=user)

    # Rebuild the GET-branch context exactly as the view does: a paginated set
    # of available lists plus the campaign's current lists / pending invitations
    # (both empty here, so the "Campaign Gangs" section is skipped).
    available = (
        List.objects.filter(id=lst.id)
        .select_related("content_house", "owner")
        .prefetch_related("packs")
        .order_by("name")
    )
    page_obj = Paginator(available, 20).get_page(None)

    campaign_packs = campaign.packs.all()
    context = {
        "campaign": campaign,
        "is_admin": True,
        "lists": page_obj,
        "page_obj": page_obj,
        "error_message": None,
        "current_lists": campaign.lists.all(),
        "pending_invitations": [],
        "campaign_packs": campaign_packs,
        "has_campaign_packs": campaign_packs.exists(),
        "show_pack_confirmation": False,
        "pack_confirm_list": None,
        "pack_confirm_packs": None,
    }
    request = _request(user, f"/campaign/{campaign.id}/lists")
    assert_equivalent("core/campaign/campaign_add_lists.html", context, request)
