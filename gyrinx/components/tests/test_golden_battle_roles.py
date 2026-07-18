"""Golden-equivalence test for the battle roles assignment form page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_battle_roles_matches_legacy(user, campaign, make_list):
    from gyrinx.core.forms.battle import BattleRolesForm
    from gyrinx.core.models import Battle

    # A battle with a participating gang, so BattleRolesForm builds a per-entry
    # role field (mirroring the view's GET branch in edit_battle_roles, which
    # guards on battle.participant_entries.exists()).
    gang = make_list("Iron Skulls", owner=user)
    campaign.lists.add(gang)
    battle = Battle.objects.create(campaign=campaign, mission="Sabotage", owner=user)
    battle.set_participants([gang])

    form = BattleRolesForm(battle=battle)
    request = _request(user)
    context = {"form": form, "battle": battle}
    assert_equivalent("core/battle/battle_roles.html", context, request)
