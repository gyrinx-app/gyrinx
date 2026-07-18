"""Golden-equivalence test: battle detail page matches its legacy template."""

from __future__ import annotations

import datetime

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models import Battle, BattleNote, CampaignAction
from gyrinx.core.views.battle import BattleDetailView


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_battle_detail_matches_legacy(user, campaign, make_list):
    # A battle owned by the campaign owner, with one participating gang, a
    # battle report note, and an associated campaign action — this exercises the
    # header actions, participants table (with the "Add crew" affordance), the
    # related-actions section, and the battle-reports section in one context.
    gang = make_list("Iron Skulls", owner=user)
    battle = Battle.objects.create(
        campaign=campaign,
        mission="Ambush",
        owner=user,
        date=datetime.date(2024, 6, 15),
    )
    battle.set_participants([gang])
    BattleNote.objects.create(
        battle=battle, owner=user, content="<p>A hard-fought scrap.</p>"
    )
    CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        battle=battle,
        description="Battle created: Ambush",
        owner=user,
    )

    request = _request(user, path=f"/battle/{battle.id}")

    # Build the exact context BattleDetailView produces for a GET.
    view = BattleDetailView()
    view.request = request
    view.kwargs = {"id": str(battle.id)}
    view.object = view.get_object()
    context = view.get_context_data(object=view.object)

    assert_equivalent("core/battle/battle.html", context, request)
