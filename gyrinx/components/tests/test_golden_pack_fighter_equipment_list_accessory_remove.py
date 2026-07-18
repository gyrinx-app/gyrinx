"""Golden-equivalence test for the pack fighter equipment-list accessory remove page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.equipment_list import (
    ContentFighterEquipmentListWeaponAccessory,
)
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_fighter_equipment_list_accessory_remove_matches_legacy(
    user, content_fighter, make_weapon_accessory
):
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user)
    fighter_ct = ContentType.objects.get_for_model(ContentFighter)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=fighter_ct,
        object_id=content_fighter.id,
        owner=user,
    )
    accessory = make_weapon_accessory("Red-Dot Laser Sight")
    row = ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=content_fighter,
        weapon_accessory=accessory,
        cost=10,
    )
    request = _request(user)
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": content_fighter,
        "row": row,
    }
    assert_equivalent(
        "core/pack/pack_fighter_equipment_list_accessory_remove.html",
        context,
        request,
    )
