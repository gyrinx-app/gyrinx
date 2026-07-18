"""Golden-equivalence test: add-injury page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models import ContentInjury, ContentInjuryDefaultOutcome
from gyrinx.core.forms.list import AddInjuryForm


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_add_injury_matches_legacy(user, make_list, make_list_fighter):
    ContentInjury.objects.create(
        name="Eye Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    ContentInjury.objects.create(
        name="Humiliated",
        phase=ContentInjuryDefaultOutcome.CONVALESCENCE,
    )

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    form = AddInjuryForm(fighter=fighter)

    request = _request(user)
    context = {
        "form": form,
        "list": lst,
        "fighter": fighter,
    }
    assert_equivalent("core/list_fighter_add_injury.html", context, request)
