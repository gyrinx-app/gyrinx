"""Golden-equivalence test for the pack add-weapon mode-select page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_weapon_mode_select_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)
    request = _request(user)
    context = {
        "pack": pack,
        "back_url": reverse("core:pack", args=(pack.id,)) + "#weapon",
        "add_weapon_url": reverse("core:pack-add-item", args=(pack.id, "weapon")),
    }
    assert_equivalent("core/pack/pack_weapon_mode_select.html", context, request)
