"""Golden-equivalence test: vehicle selection (step 1) page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_vehicle_select_matches_legacy(user, make_list):
    from gyrinx.core.forms.vehicle import VehicleSelectionForm

    lst = make_list("Iron Skulls", owner=user)
    # Mirror the view GET branch: unbound form built with the list instance.
    form = VehicleSelectionForm(list_instance=lst)
    request = _request(user)
    context = {
        "form": form,
        "list": lst,
        "step": 1,
        "total_steps": 3,
    }
    assert_equivalent("core/vehicle_select.html", context, request)
