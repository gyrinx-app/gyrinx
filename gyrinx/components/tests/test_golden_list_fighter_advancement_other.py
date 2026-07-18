"""Golden-equivalence test for the 'other' advancement description page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/", data=None):
    request = RequestFactory().get(path, data or {})
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_advancement_other_matches_legacy(
    user, make_list, make_list_fighter
):
    from gyrinx.core.forms.advancement import OtherAdvancementForm
    from gyrinx.core.models.list import List
    from gyrinx.core.views.fighter.advancements import AdvancementFlowParams

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    # Mirror the view's GET branch: parse params from the query string and
    # build an unbound OtherAdvancementForm.
    request = _request(
        user, path="/", data={"advancement_choice": "other", "xp_cost": "6"}
    )
    params = AdvancementFlowParams.model_validate(request.GET.dict())
    form = OtherAdvancementForm()

    context = {
        "form": form,
        "fighter": fighter,
        "list": lst,
        "params": params,
        "is_campaign_mode": lst.status == List.CAMPAIGN_MODE,
    }
    assert_equivalent("core/list_fighter_advancement_other.html", context, request)
