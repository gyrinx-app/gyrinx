"""Golden-equivalence test for the pack add-fighter stat-entry page."""

from __future__ import annotations

import uuid
from urllib.parse import urlencode

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.views.pack import AddFighterFlowParams
from gyrinx.models import FighterCategoryChoices


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_item_add_stats_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)

    # Build the flow params exactly as the view's GET branch does. VEHICLE
    # exercises the info alert branch.
    params = AddFighterFlowParams(
        type="War Rig",
        category=FighterCategoryChoices.VEHICLE.value,
        house_id=uuid.uuid4(),
        base_cost=150,
    )

    # Mirror the view's stat_context shape (list of plain dicts).
    stat_definitions = [
        {"field_name": "movement", "short_name": "M", "placeholder": '4"', "value": ""},
        {
            "field_name": "weapon_skill",
            "short_name": "WS",
            "placeholder": "3+",
            "value": "",
        },
        {"field_name": "strength", "short_name": "S", "placeholder": "3", "value": ""},
    ]

    query_string = urlencode(
        params.model_dump(mode="json", exclude_none=True), doseq=True
    )
    category_display = dict(FighterCategoryChoices.choices).get(
        params.category, params.category
    )

    context = {
        "pack": pack,
        "params": params,
        "stat_definitions": stat_definitions,
        "query_string": query_string,
        "save_and_add_another": False,
        "house_name": "Ash Wastes Nomads",
        "category_display": category_display,
        "back_url": reverse("core:pack", args=(pack.id,)) + "#fighter",
    }
    request = _request(user)
    assert_equivalent("core/pack/pack_item_add_stats.html", context, request)
