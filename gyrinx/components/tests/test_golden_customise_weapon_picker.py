"""Golden-equivalence test for the customise-existing-weapon picker page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.views.pack import _pack_url, _pack_weapon_picker_data


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_customise_weapon_picker_matches_legacy(user, make_weapon_with_profile):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)

    # A library weapon (equipment with a weapon profile) so the picker's
    # result table + category filter render — exercising the populated
    # ``weapon_groups`` branch and the bridged shared partials.
    make_weapon_with_profile()

    request = _request(user)
    # Build the context exactly as the view's GET branch does.
    picker_data = _pack_weapon_picker_data(request, pack, include_pack_weapons=False)
    context = {
        "pack": pack,
        "target_label": "weapons",
        "back_url": _pack_url(pack),
        **picker_data,
    }
    assert_equivalent("core/pack/customise_weapon_picker.html", context, request)
