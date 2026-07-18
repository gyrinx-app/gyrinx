"""Golden-equivalence test for the pack fighter default gear add page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.core.models.pack import CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_fighter_default_gear_add_matches_legacy(
    user, content_fighter, make_pack, make_equipment
):
    pack = make_pack("Test Pack", owner=user)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=content_fighter.pk,
        owner=user,
    )

    armour = make_equipment("Flak Armour", category="Armour", cost="10")
    field = make_equipment("Bio-scanner", category="Field Armour", cost="25")

    categories = {
        armour.category.name: [armour],
        field.category.name: [field],
    }

    request = _request(user)
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": content_fighter,
        "categories": categories,
        "search_q": "arm",
        "error_message": None,
    }
    assert_equivalent("core/pack/pack_fighter_default_gear_add.html", context, request)
