"""Golden-equivalence test for the pack gear/weapon Modifiers tab."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models import ContentEquipment
from gyrinx.core.forms.pack import EquipmentModifiersForm
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_item_modifiers_matches_legacy(user, make_equipment):
    # Seed a fighter-side stat so the mod picker renders a stat row (matches
    # production where migration 0148 seeds the canonical stats).
    from gyrinx.content.models.statline import (
        ContentStat,
        ContentStatlineType,
        ContentStatlineTypeStat,
    )

    stat, _ = ContentStat.objects.get_or_create(
        field_name="movement",
        defaults={"short_name": "M", "full_name": "Movement", "is_inches": True},
    )
    fighter_type, _ = ContentStatlineType.objects.get_or_create(name="Fighter")
    ContentStatlineTypeStat.objects.get_or_create(
        statline_type=fighter_type, stat=stat, defaults={"position": 1}
    )

    pack = CustomContentPack.objects.create(name="Test Pack", owner=user, listed=True)
    gear = make_equipment("Pack Plate", category="Pack Gear Cat", cost=10)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentEquipment),
        object_id=gear.pk,
        owner=user,
    )

    # Mirror the GET branch of pack.pack_item_modifiers.
    form = EquipmentModifiersForm(instance=gear, pack=pack)

    request = _request(user)
    context = {
        "form": form,
        "pack": pack,
        "pack_item": pack_item,
        "content_obj": gear,
        "label": "Gear",
        "icon": "bi-wrench",
        "slug": "gear",
        "back_url": reverse("core:pack", args=(pack.id,)) + f"#item-{pack_item.id}",
    }
    assert_equivalent("core/pack/pack_item_modifiers.html", context, request)
