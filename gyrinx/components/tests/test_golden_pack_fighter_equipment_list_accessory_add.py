"""Golden-equivalence test for the pack fighter equipment-list accessory-add page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.weapon import ContentWeaponAccessory
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_fighter_equipment_list_accessory_add_matches_legacy(
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

    make_weapon_accessory("Suspensor", cost=35)
    make_weapon_accessory("Hotshot Las Pack", cost=25)
    accessories = list(
        ContentWeaponAccessory.objects.with_packs([pack]).order_by("name")
    )

    request = _request(user)
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": content_fighter,
        "accessories": accessories,
        "error_message": None,
    }
    assert_equivalent(
        "core/pack/pack_fighter_equipment_list_accessory_add.html", context, request
    )
