"""Golden-equivalence test: campaign_packs page matches its legacy template."""

from __future__ import annotations

import pytest
from django.db import models as dj_models
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_packs_matches_legacy(user, make_campaign, make_list):
    campaign = make_campaign("Underhive Wars")

    # A pack allowed in the campaign, plus a candidate pack to add.
    allowed_pack = CustomContentPack.objects.create(
        name="Alpha Pack", owner=user, listed=True
    )
    campaign.packs.add(allowed_pack)
    CustomContentPack.objects.create(name="Beta Pack", owner=user, listed=True)

    # The user's gang in the campaign (drives the "Add to…" dropdown).
    lst = make_list("Iron Skulls", owner=user)
    campaign.lists.add(lst)

    request = _request(user, path=f"/campaign/{campaign.id}/packs")

    # Mirror the view's GET data-building so pack annotations match.
    is_admin = campaign.is_admin(user)
    campaign_packs_qs = campaign.packs.select_related("owner").order_by("name")
    required_pack_ids = set(
        campaign.pack_links.filter(required=True).values_list("pack_id", flat=True)
    )
    user_campaign_lists = (
        campaign.lists.filter(owner=user, archived=False)
        .select_related("content_house")
        .prefetch_related("packs")
        .order_by("name")
    )
    subscribed_by_pack = {}
    for member in user_campaign_lists:
        for pack in member.packs.all():
            subscribed_by_pack.setdefault(pack.id, set()).add(member.id)

    packs_with_lists = []
    for pack in campaign_packs_qs:
        subscribed_ids = subscribed_by_pack.get(pack.id, set())
        pack.unsubscribed_user_lists = [
            member for member in user_campaign_lists if member.id not in subscribed_ids
        ]
        pack.is_required = pack.id in required_pack_ids
        packs_with_lists.append(pack)

    can_edit_required = (
        is_admin and not campaign.archived and not campaign.is_post_campaign
    )
    available_packs = (
        CustomContentPack.objects.filter(
            dj_models.Q(owner=user) | dj_models.Q(listed=True),
            archived=False,
        )
        .exclude(id__in=campaign_packs_qs.values_list("id", flat=True))
        .select_related("owner")
        .order_by("name")
    )

    context = {
        "campaign": campaign,
        "campaign_packs": packs_with_lists,
        "available_packs": available_packs,
        "is_admin": is_admin,
        "user_campaign_lists": user_campaign_lists,
        "search_query": "",
        "show_my_packs": False,
        "can_edit_required": can_edit_required,
    }
    assert_equivalent("core/campaign/campaign_packs.html", context, request)
