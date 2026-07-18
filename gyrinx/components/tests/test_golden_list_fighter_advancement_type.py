"""Golden-equivalence test for the advancement type selection page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/", data=None):
    request = RequestFactory().get(path, data or {})
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_advancement_type_matches_legacy(
    user, make_list, make_list_fighter
):
    from gyrinx.core.forms.advancement import AdvancementTypeForm
    from gyrinx.core.models.list import List
    from gyrinx.core.views.fighter.advancements import AdvancementBaseParams

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    # Mirror the view's GET branch: parse base params from the query string,
    # build the unbound AdvancementTypeForm with the action-derived initial.
    request = _request(user)
    is_campaign_mode = lst.status == List.CAMPAIGN_MODE
    params = AdvancementBaseParams.model_validate(request.GET.dict())
    campaign_action = None
    initial = {
        **params.model_dump(mode="json", exclude_none=True),
        **AdvancementTypeForm.get_initial_for_action(campaign_action),
    }
    form = AdvancementTypeForm(initial=initial, fighter=fighter)

    context = {
        "form": form,
        "fighter": fighter,
        "list": lst,
        "campaign_action": campaign_action,
        "is_campaign_mode": is_campaign_mode,
        "steps": 3 if is_campaign_mode else 2,
        "current_step": 2 if is_campaign_mode else 1,
        "progress": 66 if is_campaign_mode else 50,
        "advancement_configs": form.get_all_configs_json(),
    }
    assert_equivalent("core/list_fighter_advancement_type.html", context, request)
