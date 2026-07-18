"""Golden-equivalence test: campaign actions listing matches its legacy template."""

from __future__ import annotations

import pytest
from django.core.paginator import Paginator
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.battle import Battle
from gyrinx.core.models.campaign import Campaign, CampaignAction


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _build_context(campaign, *, can_log_actions):
    """Reproduce the ListView GET-branch context (get_queryset + get_context_data)."""
    actions_qs = campaign.actions.select_related("user", "list", "battle").order_by(
        "-created"
    )
    paginator = Paginator(actions_qs, 50)
    page_obj = paginator.get_page(1)
    return {
        "campaign": campaign,
        "object_list": page_obj.object_list,
        "actions": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "is_paginated": page_obj.has_other_pages(),
        "campaign_lists": campaign.lists.select_related(
            "owner", "content_house"
        ).order_by("name"),
        "action_authors": campaign.actions.values_list("user__id", "user__username")
        .distinct()
        .order_by("user__username"),
        "campaign_battles": campaign.battles.select_related("owner")
        .prefetch_related("participants", "winners")
        .order_by("-date", "-created"),
        "can_log_actions": can_log_actions,
    }


@pytest.mark.django_db
def test_campaign_actions_matches_legacy(user, make_campaign, make_list):
    campaign = make_campaign("Underhive Wars", status=Campaign.IN_PROGRESS)
    lst = make_list("Iron Skulls", owner=user)
    campaign.lists.add(lst)
    Battle.objects.create(campaign=campaign, mission="Sabotage", owner=user)
    CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        owner=user,
        description="Scouted the ash wastes",
    )

    context = _build_context(campaign, can_log_actions=True)
    request = _request(user, reverse("core:campaign-actions", args=[campaign.id]))
    assert_equivalent("core/campaign/campaign_actions.html", context, request)


@pytest.mark.django_db
def test_campaign_actions_empty_matches_legacy(make_user, make_campaign):
    other = make_user("owner", "password")
    viewer = make_user("viewer", "password")
    campaign = make_campaign("Empty Campaign", owner=other, status=Campaign.IN_PROGRESS)

    # Viewer neither owns the campaign nor has a list in it: no "Log Action"
    # button, and no actions/lists/battles so every filter loop and the feed
    # render their empty states.
    context = _build_context(campaign, can_log_actions=False)
    request = _request(viewer, reverse("core:campaign-actions", args=[campaign.id]))
    assert_equivalent("core/campaign/campaign_actions.html", context, request)
