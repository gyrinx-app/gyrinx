"""Golden-equivalence test: list_packs component matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_packs_matches_legacy(user, make_user, make_list):
    """Populated: campaign recommendations, subscribed (required + not,
    owner-link + span), and available (listed-link + span, summary + none)."""
    lst = make_list("Iron Skulls", owner=user)
    other = make_user("otheruser", "password")

    # Campaign-recommended packs: a listed one (link + summary) and an
    # unlisted one owned by someone else (span, no summary).
    camp_listed = CustomContentPack.objects.create(
        owner=other,
        name="Campaign Listed Pack",
        summary="<p>Camp <i>rec</i> gear and rules for the wastes.</p>",
        listed=True,
    )
    camp_hidden = CustomContentPack.objects.create(
        owner=other,
        name="Campaign Hidden Pack",
        summary="",
        listed=False,
    )
    campaign_packs = [camp_listed, camp_hidden]

    # Subscribed packs: one owned by the user with no required-by campaigns
    # (link + summary + Remove form), one required by campaigns owned by
    # someone else (span, no summary, warning badge, no Remove form).
    sub_owned = CustomContentPack.objects.create(
        owner=user,
        name="Owned Subscribed Pack",
        summary="<p>Owned <b>subscribed</b> content.</p>",
        listed=False,
    )
    sub_owned.required_by_campaigns = []
    sub_required = CustomContentPack.objects.create(
        owner=other,
        name="Required Subscribed Pack",
        summary="",
        listed=False,
    )
    sub_required.required_by_campaigns = ["Underhive Wars", "Gang War"]
    subscribed_packs = [sub_owned, sub_required]

    # Available packs: a listed pack (link + summary) and an unlisted pack
    # owned by someone else (span, no summary).
    avail_listed = CustomContentPack.objects.create(
        owner=other,
        name="Available Listed Pack",
        summary="Plain available summary text.",
        listed=True,
    )
    avail_hidden = CustomContentPack.objects.create(
        owner=other,
        name="Available Hidden Pack",
        summary="",
        listed=False,
    )
    available_packs = (
        CustomContentPack.objects.filter(id__in=[avail_listed.id, avail_hidden.id])
        .select_related("owner")
        .order_by("name")
    )

    request = _request(user)
    context = {
        "list": lst,
        "subscribed_packs": subscribed_packs,
        "available_packs": available_packs,
        "campaign_packs": campaign_packs,
        "search_query": "",
        "show_my_packs": False,
    }
    assert_equivalent("core/list_packs.html", context, request)


@pytest.mark.django_db
def test_list_packs_filtered_empty_matches_legacy(user, make_list):
    """Filtered/empty: no campaign packs, no subscriptions, no available results
    for a search query, "Your Packs only" on (Clear link + checked switch)."""
    lst = make_list("Iron Skulls", owner=user)

    request = _request(user)
    context = {
        "list": lst,
        "subscribed_packs": [],
        "available_packs": CustomContentPack.objects.none(),
        "campaign_packs": CustomContentPack.objects.none(),
        "search_query": "wasteland",
        "show_my_packs": True,
    }
    assert_equivalent("core/list_packs.html", context, request)


@pytest.mark.django_db
def test_list_packs_empty_no_search_matches_legacy(user, make_list):
    """Empty available list with no search query -> "No additional packs
    available." and no Clear link."""
    lst = make_list("Iron Skulls", owner=user)

    request = _request(user)
    context = {
        "list": lst,
        "subscribed_packs": [],
        "available_packs": CustomContentPack.objects.none(),
        "campaign_packs": CustomContentPack.objects.none(),
        "search_query": "",
        "show_my_packs": False,
    }
    assert_equivalent("core/list_packs.html", context, request)
