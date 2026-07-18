"""Golden-equivalence test for the house-rule archive confirmation page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_house_rule_delete_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="Ash Wastes Rules", owner=user)
    request = _request(user)
    context = {"pack": pack, "pack_item": None}
    assert_equivalent("core/pack/house_rule_delete.html", context, request)
