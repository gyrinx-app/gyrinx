"""Golden-equivalence test for the crew member loadout page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_crew_member_loadout_matches_legacy(
    user, list_with_campaign, make_list_fighter
):
    from gyrinx.core.forms.crew import CrewMemberLoadoutForm
    from gyrinx.core.models import Battle
    from gyrinx.core.models.crew import Crew, CrewMember

    gang = list_with_campaign
    fighter = make_list_fighter(gang, "Specialist")
    battle = Battle.objects.create(campaign=gang.campaign, mission="Ambush", owner=user)
    battle.set_participants([gang])
    crew = Crew.objects.create(battle=battle, list=gang, owner=user, status=Crew.LOCKED)
    member = CrewMember.objects.create(crew=crew, list_fighter=fighter, owner=user)
    form = CrewMemberLoadoutForm(instance=member)

    request = _request(user)
    context = {
        "form": form,
        "crew": crew,
        "battle": crew.battle,
        "member": member,
    }
    assert_equivalent("core/crew/crew_member_loadout.html", context, request)
