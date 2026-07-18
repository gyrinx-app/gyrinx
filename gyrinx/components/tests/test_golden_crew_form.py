"""Golden-equivalence test: crew_form page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_crew_form_create_matches_legacy(
    user, campaign, list_with_campaign, make_list_fighter
):
    from gyrinx.core.forms.crew import CrewForm
    from gyrinx.core.models import Battle

    gang = list_with_campaign
    make_list_fighter(gang, "Ganger 1")
    battle = Battle.objects.create(campaign=campaign, mission="Ambush", owner=user)
    battle.set_participants([gang])

    form = CrewForm(gang=gang)
    request = _request(user)
    context = {"form": form, "battle": battle, "gang": gang, "is_create": True}
    assert_equivalent("core/crew/crew_form.html", context, request)


@pytest.mark.django_db
def test_crew_form_edit_matches_legacy(user, campaign, list_with_campaign):
    from gyrinx.core.forms.crew import CrewForm
    from gyrinx.core.models import Battle
    from gyrinx.core.models.crew import Crew

    gang = list_with_campaign
    battle = Battle.objects.create(campaign=campaign, mission="Ambush", owner=user)
    battle.set_participants([gang])
    crew = Crew.objects.create(battle=battle, list=gang, owner=user)

    form = CrewForm(instance=crew, gang=gang)
    request = _request(user)
    context = {"form": form, "battle": crew.battle, "gang": crew.list, "crew": crew}
    assert_equivalent("core/crew/crew_form.html", context, request)
