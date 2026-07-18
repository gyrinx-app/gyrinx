"""Golden-equivalence test: pack fighter equipment-list item cost edit page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.equipment import (
    ContentEquipment,
    ContentEquipmentCategory,
)
from gyrinx.content.models.equipment_list import ContentFighterEquipmentListItem
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_fighter_equipment_list_item_edit_matches_legacy(
    user, content_house, make_content_fighter
):
    pack = CustomContentPack.objects.create(
        name="Test Pack",
        summary="A test pack",
        listed=True,
        owner=user,
    )
    fighter = make_content_fighter("Pack Fighter", "ganger", content_house, 50)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(fighter),
        object_id=fighter.pk,
        owner=user,
    )

    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Personal Equipment",
        defaults={"group": "Gear"},
    )
    gear = ContentEquipment.objects.create(
        name="Mesh Armour",
        category=category,
        cost="15",
    )
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=gear, cost=15
    )

    request = _request(user)
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": fighter,
        "eli": eli,
        "group_items": [eli],
    }
    assert_equivalent(
        "core/pack/pack_fighter_equipment_list_item_edit.html", context, request
    )
