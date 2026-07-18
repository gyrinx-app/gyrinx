"""Golden-equivalence test: crew detail page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.battle import Battle
from gyrinx.core.models.crew import Crew, CrewLineItem, CrewMember


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_crew_detail_matches_legacy(
    user, campaign, list_with_campaign, make_list_fighter
):
    gang = list_with_campaign
    fighter = make_list_fighter(gang, "Ganger 0")

    battle = Battle.objects.create(campaign=campaign, mission="Ambush", owner=user)
    battle.set_participants([gang])

    # A locked crew with a frozen attendee plus two extras (one paid from
    # credits, one free) so the receipt exercises attendees, extras, the free
    # column, subtotals and the total.
    crew = Crew.objects.create(battle=battle, list=gang, owner=user, status=Crew.LOCKED)
    CrewMember.objects.create(crew=crew, list_fighter=fighter, owner=user)
    CrewLineItem.objects.create(
        crew=crew, label="Tactics card: Ambush", cost=20, owner=user
    )
    CrewLineItem.objects.create(
        crew=crew,
        label="Free favour",
        cost=30,
        payment=Crew.PAY_FREE,
        reason="House patronage",
        owner=user,
    )

    request = _request(user, path=f"/battle/{battle.id}/crew/{crew.id}")
    context = {
        "crew": crew,
        "battle": crew.battle,
        "can_manage": crew.can_manage(user),
        "receipt": crew.receipt(),
    }
    assert_equivalent("core/crew/crew.html", context, request)
