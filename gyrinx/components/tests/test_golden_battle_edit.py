"""Golden-equivalence test for the battle-edit form page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_battle_edit_matches_legacy(user, campaign, list_with_campaign):
    from gyrinx.core.forms.battle import BattleForm
    from gyrinx.core.models import Battle

    battle = Battle.objects.create(campaign=campaign, mission="Sabotage", owner=user)

    # Mirror the view's GET branch (edit_battle in core/views/battle.py).
    form = BattleForm(instance=battle, campaign=battle.campaign, include_winners=True)
    request = _request(user)
    context = {"form": form, "battle": battle}
    assert_equivalent("core/battle/battle_edit.html", context, request)
