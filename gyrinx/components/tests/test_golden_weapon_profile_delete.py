"""Golden-equivalence test for the weapon-profile archive confirmation page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_weapon_profile_delete_matches_legacy(user):
    from gyrinx.content.models import ContentEquipment, ContentWeaponProfile
    from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem

    pack = CustomContentPack.objects.create(owner=user, name="Ash Wastes Pack")
    equipment = ContentEquipment.objects.create(name="Autogun", cost="")
    profile = ContentWeaponProfile.objects.create(
        equipment=equipment, name="Rapid Fire"
    )
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentEquipment),
        object_id=equipment.pk,
    )

    # Mirror the view's GET branch context construction.
    back_url = reverse("core:pack", args=(pack.id,)) + f"#item-{pack_item.id}"
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "equipment": equipment,
        "profile": profile,
        "slug": "weapon",
        "back_url": back_url,
        "form_action_url": reverse(
            "core:pack-delete-weapon-profile",
            args=(pack.id, pack_item.id, profile.id),
        ),
    }
    request = _request(user)
    assert_equivalent("core/pack/weapon_profile_delete.html", context, request)
