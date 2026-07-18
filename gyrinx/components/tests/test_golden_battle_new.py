"""Golden-equivalence test for the new-battle form page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_battle_new_matches_legacy(user, campaign, make_list):
    from gyrinx.core.forms.battle import BattleForm

    # A campaign gang so the participants field renders with a real option,
    # mirroring the view's GET branch (which builds ``BattleForm(campaign=campaign)``).
    lst = make_list("Iron Skulls", owner=user)
    campaign.lists.add(lst)

    form = BattleForm(campaign=campaign)
    request = _request(user)
    context = {"form": form, "campaign": campaign}
    assert_equivalent("core/battle/battle_new.html", context, request)
