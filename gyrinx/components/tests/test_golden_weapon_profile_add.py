"""Golden-equivalence test for the add-weapon-profile pack editor page."""

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
def test_weapon_profile_add_matches_legacy(user):
    from gyrinx.content.models import ContentEquipment
    from gyrinx.core.forms.pack import ContentWeaponProfilePackForm
    from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
    from gyrinx.core.views.pack import _build_weapon_stat_context, _pack_url

    pack = CustomContentPack.objects.create(name="Ash Wastes Pack", owner=user)
    equipment = ContentEquipment.objects.create(name="Autogun", cost="")
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentEquipment),
        object_id=equipment.pk,
    )

    request = _request(user)
    # Mirror the add_weapon_profile view's GET branch context construction.
    context = {
        "form": ContentWeaponProfilePackForm(pack=pack),
        "pack": pack,
        "pack_item": pack_item,
        "equipment": equipment,
        "slug": "weapon",
        "back_url": _pack_url(pack, f"item-{pack_item.id}"),
        "form_action_url": reverse(
            "core:pack-add-weapon-profile", args=(pack.id, pack_item.id)
        ),
        "weapon_stat_fields": _build_weapon_stat_context(request),
    }
    assert_equivalent("core/pack/weapon_profile_add.html", context, request)


@pytest.mark.django_db
def test_weapon_profile_add_customised_matches_legacy(user):
    from gyrinx.content.models import ContentEquipment
    from gyrinx.core.forms.pack import ContentWeaponProfilePackForm
    from gyrinx.core.models.pack import CustomContentPack
    from gyrinx.core.views.pack import (
        _build_weapon_stat_context,
        _customise_weapon_back_url,
    )

    pack = CustomContentPack.objects.create(name="Ash Wastes Pack", owner=user)
    equipment = ContentEquipment.objects.create(name="Autogun", cost="")

    request = _request(user)
    # Mirror the add_customised_weapon_profile view's GET branch: this variant
    # additionally exposes ``customise_another_url``.
    context = {
        "form": ContentWeaponProfilePackForm(pack=pack),
        "pack": pack,
        "equipment": equipment,
        "slug": "weapon",
        "back_url": _customise_weapon_back_url(pack, equipment),
        "form_action_url": reverse(
            "core:pack-customise-weapon-profile-add",
            args=(pack.id, equipment.id),
        ),
        "customise_another_url": reverse(
            "core:pack-customise-weapon-picker", args=(pack.id,)
        ),
        "weapon_stat_fields": _build_weapon_stat_context(request),
    }
    assert_equivalent("core/pack/weapon_profile_add.html", context, request)
