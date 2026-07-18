"""Golden-equivalence test: vehicle confirmation (step 3) page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_vehicle_confirm_with_crew_matches_legacy(
    user, make_list, make_content_fighter, content_house
):
    from gyrinx.content.models import ContentEquipment
    from gyrinx.core.forms.vehicle import VehicleConfirmationForm
    from gyrinx.models import FighterCategoryChoices

    lst = make_list("Iron Skulls", owner=user)
    vehicle_equipment = ContentEquipment.objects.create(name="Ridge Runner", cost="120")
    crew_fighter = make_content_fighter(
        type="Crew",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=50,
    )
    # Mirror the view GET branch: an unbound confirmation form with pre-computed
    # costs, plus the resolved crew fighter (select_crew action).
    form = VehicleConfirmationForm()
    request = _request(user)
    context = {
        "form": form,
        "list": lst,
        "vehicle_equipment": vehicle_equipment,
        "crew_fighter": crew_fighter,
        "crew_name": "Sparky",
        "vehicle_cost": 120,
        "crew_cost": 50,
        "total_cost": 170,
        "step": 3,
        "total_steps": 3,
    }
    assert_equivalent("core/vehicle_confirm.html", context, request)


@pytest.mark.django_db
def test_vehicle_confirm_stash_matches_legacy(user, make_list):
    from gyrinx.content.models import ContentEquipment
    from gyrinx.core.forms.vehicle import VehicleConfirmationForm

    lst = make_list("Iron Skulls", owner=user)
    vehicle_equipment = ContentEquipment.objects.create(name="Ridge Runner", cost="120")
    # add_to_stash action: no crew resolved, crew_cost is 0.
    form = VehicleConfirmationForm()
    request = _request(user)
    context = {
        "form": form,
        "list": lst,
        "vehicle_equipment": vehicle_equipment,
        "crew_fighter": None,
        "crew_name": None,
        "vehicle_cost": 120,
        "crew_cost": 0,
        "total_cost": 120,
        "step": 3,
        "total_steps": 3,
    }
    assert_equivalent("core/vehicle_confirm.html", context, request)
