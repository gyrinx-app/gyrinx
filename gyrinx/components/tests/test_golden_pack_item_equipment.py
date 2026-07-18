"""Golden-equivalence test for core/pack/pack_item_equipment.html."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
from gyrinx.core.views.pack import (
    _load_default_equipment_context,
    _load_equipment_list_accessory_context,
    _load_equipment_list_context,
    _load_fighter_preview_context,
    _pack_url,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_item_equipment_matches_legacy(user, content_fighter):
    # Mirror the GET branch of pack_item_equipment: a fighter pack item with
    # the default-equipment, equipment-list, and fighter-preview context built
    # by the same view helpers.
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=content_fighter.pk,
        owner=user,
    )

    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": content_fighter,
        "label": "Fighter or Vehicle",
        "icon": "bi-person",
        "back_url": _pack_url(pack, f"item-{pack_item.id}"),
    }
    context.update(_load_default_equipment_context(pack, content_fighter))
    context.update(_load_equipment_list_context(content_fighter))
    context.update(_load_equipment_list_accessory_context(content_fighter))
    context.update(_load_fighter_preview_context(pack, content_fighter))

    request = _request(user)
    assert_equivalent("core/pack/pack_item_equipment.html", context, request)
