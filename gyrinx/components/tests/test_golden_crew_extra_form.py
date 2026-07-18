"""Golden-equivalence test for the crew extra (line item) form page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.forms.crew import CrewLineItemForm
from gyrinx.core.models import Battle
from gyrinx.core.models.crew import Crew


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_crew_extra_form_matches_legacy(user, list_with_campaign):
    battle = Battle.objects.create(
        campaign=list_with_campaign.campaign, mission="Ambush", owner=user
    )
    battle.set_participants([list_with_campaign])
    crew = Crew.objects.create(battle=battle, list=list_with_campaign, owner=user)

    # GET add branch: no item, unbound form.
    form = CrewLineItemForm(instance=None)
    request = _request(user)
    context = {
        "form": form,
        "crew": crew,
        "battle": crew.battle,
        "item": None,
    }
    assert_equivalent("core/crew/crew_extra_form.html", context, request)
