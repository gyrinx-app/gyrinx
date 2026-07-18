"""Golden-equivalence test for the edit-weapon-profile pack editor page."""

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


def _stat_values(profile):
    """Mirror the edit views' GET-branch stat context (value from the profile)."""
    from gyrinx.core.views.pack import _WEAPON_PROFILE_STAT_FIELDS

    return [
        {
            "field_name": field_name,
            "short_name": short_name,
            "placeholder": placeholder,
            "value": getattr(profile, field_name, ""),
        }
        for field_name, short_name, placeholder in _WEAPON_PROFILE_STAT_FIELDS
    ]


@pytest.mark.django_db
def test_weapon_profile_edit_matches_legacy(user):
    from gyrinx.content.models import ContentEquipment, ContentWeaponProfile
    from gyrinx.core.forms.pack import ContentWeaponProfilePackForm
    from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
    from gyrinx.core.views.pack import _pack_url

    pack = CustomContentPack.objects.create(name="Ash Wastes Pack", owner=user)
    equipment = ContentEquipment.objects.create(name="Autogun", cost="")
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentEquipment),
        object_id=equipment.pk,
    )
    # A named profile: exercises the ": name" heading and the Archive link.
    profile = ContentWeaponProfile.objects.create(
        equipment=equipment,
        name="Rapid Fire",
        cost=10,
        range_short='8"',
        range_long='24"',
        accuracy_short="+1",
        strength="3",
        damage="1",
        ammo="4+",
    )

    request = _request(user)
    # Mirror the edit_weapon_profile view's GET branch context construction.
    context = {
        "form": ContentWeaponProfilePackForm(instance=profile, pack=pack),
        "pack": pack,
        "pack_item": pack_item,
        "equipment": equipment,
        "profile": profile,
        "slug": "weapon",
        "back_url": _pack_url(pack, f"item-{pack_item.id}"),
        "form_action_url": reverse(
            "core:pack-edit-weapon-profile",
            args=(pack.id, pack_item.id, profile.id),
        ),
        "delete_url": reverse(
            "core:pack-delete-weapon-profile",
            args=(pack.id, pack_item.id, profile.id),
        ),
        "weapon_stat_values": _stat_values(profile),
    }
    assert_equivalent("core/pack/weapon_profile_edit.html", context, request)


@pytest.mark.django_db
def test_weapon_profile_edit_customised_matches_legacy(user):
    from gyrinx.content.models import ContentEquipment, ContentWeaponProfile
    from gyrinx.core.forms.pack import ContentWeaponProfilePackForm
    from gyrinx.core.models.pack import CustomContentPack
    from gyrinx.core.views.pack import _customise_weapon_back_url

    pack = CustomContentPack.objects.create(name="Ash Wastes Pack", owner=user)
    equipment = ContentEquipment.objects.create(name="Autogun", cost="")
    # An unnamed (standard) profile: no ": name" heading, no Archive link.
    # The customised variant additionally exposes ``customise_another_url``.
    profile = ContentWeaponProfile.objects.create(
        equipment=equipment,
        name="",
        cost=0,
        range_short='8"',
        strength="3",
        damage="1",
    )

    request = _request(user)
    # Mirror the edit_customised_weapon_profile view's GET branch.
    context = {
        "form": ContentWeaponProfilePackForm(instance=profile, pack=pack),
        "pack": pack,
        "equipment": equipment,
        "profile": profile,
        "slug": "weapon",
        "back_url": _customise_weapon_back_url(pack, equipment),
        "form_action_url": reverse(
            "core:pack-customise-weapon-profile-edit",
            args=(pack.id, equipment.id, profile.id),
        ),
        "delete_url": reverse(
            "core:pack-customise-weapon-profile-delete",
            args=(pack.id, equipment.id, profile.id),
        ),
        "customise_another_url": reverse(
            "core:pack-customise-weapon-picker", args=(pack.id,)
        ),
        "weapon_stat_values": _stat_values(profile),
    }
    assert_equivalent("core/pack/weapon_profile_edit.html", context, request)
