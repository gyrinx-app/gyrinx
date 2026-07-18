"""Golden-equivalence test: vehicle crew selection (step 2) page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_vehicle_crew_matches_legacy(user, make_list):
    from gyrinx.content.models import ContentEquipment
    from gyrinx.core.forms.vehicle import CrewSelectionForm

    lst = make_list("Iron Skulls", owner=user)
    vehicle_equipment = ContentEquipment.objects.create(name="Ridge Runner", cost="120")
    # Mirror the view GET branch: unbound form built with the list instance and
    # the selected vehicle equipment.
    form = CrewSelectionForm(list_instance=lst, vehicle_equipment=vehicle_equipment)
    request = _request(user)
    context = {
        "form": form,
        "list": lst,
        "vehicle_equipment": vehicle_equipment,
        "step": 2,
        "total_steps": 3,
    }
    assert_equivalent("core/vehicle_crew.html", context, request)
