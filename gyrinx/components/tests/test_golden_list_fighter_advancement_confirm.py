"""Golden-equivalence test for the fighter advancement confirm page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.list import List
from gyrinx.core.views.fighter.advancements import AdvancementFlowParams


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_advancement_confirm_matches_legacy(
    user, make_list, make_list_fighter
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    # Reproduce the view's GET branch for an "other" advancement (no ContentStat
    # dependency): validate params, build the details dict and step counters.
    params = AdvancementFlowParams(
        advancement_choice="other",
        xp_cost=6,
        cost_increase=10,
        description="Extra grit",
    )
    is_campaign_mode = lst.status == List.CAMPAIGN_MODE
    stat = None
    stat_desc = params.description

    steps = 3
    if not is_campaign_mode and not params.is_other_advancement():
        steps = 2

    context = {
        "fighter": fighter,
        "list": lst,
        "details": {
            **params.model_dump(),
            "stat": stat,
            "description": stat_desc,
        },
        "is_campaign_mode": is_campaign_mode,
        "steps": steps,
        "current_step": steps,
    }

    request = _request(user)
    assert_equivalent("core/list_fighter_advancement_confirm.html", context, request)
