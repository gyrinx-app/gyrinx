"""Golden-equivalence test for the customise-existing-weapon page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.weapon import ContentWeaponProfile, ContentWeaponTrait
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
from gyrinx.core.views.pack import (
    _PackModdedProfile,
    _get_pack_and_existing_weapon,
    _pack_mods_for_target_ids,
    _pack_url,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _register_profile_item(pack, profile, user, *, archived=False):
    ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=profile.pk, owner=user, archived=archived
    )
    item.save_with_user(user=user)
    return item


@pytest.mark.django_db
def test_customise_weapon_matches_legacy(user, make_weapon_with_profile):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)

    # A library weapon with a library profile — this is the weapon being
    # customised. The library profile renders as a (non-pack-scoped) row.
    weapon, _library_profile = make_weapon_with_profile()

    # A pack-scoped profile so the pack-author edit/archive controls and the
    # "Added by this Content Pack" marker branch render.
    active_profile = ContentWeaponProfile.objects.create(
        name="Special Ammo", equipment=weapon, cost=15
    )
    _register_profile_item(pack, active_profile, user)

    # An archived pack-scoped profile so ``archived_pack_profile_count > 0`` and
    # the "Archived profiles (N)" link renders.
    archived_profile = ContentWeaponProfile.objects.create(
        name="Old Ammo", equipment=weapon, cost=10
    )
    _register_profile_item(pack, archived_profile, user, archived=True)

    request = _request(user)

    # Build the context exactly as ``customise_weapon``'s GET branch does.
    pack, equipment = _get_pack_and_existing_weapon(pack.id, weapon.id, user)
    profiles_qs = (
        ContentWeaponProfile.objects.with_packs([pack])
        .filter(equipment=equipment)
        .prefetch_related(
            Prefetch(
                "traits",
                queryset=ContentWeaponTrait.objects.all_content(),
            )
        )
    )
    profile_ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    visible_profile_ids = list(profiles_qs.values_list("pk", flat=True))
    all_profile_ids = list(
        ContentWeaponProfile.objects.all_content()
        .filter(equipment=equipment)
        .values_list("pk", flat=True)
    )
    pack_profile_object_ids = set(
        CustomContentPackItem.objects.filter(
            pack=pack,
            content_type=profile_ct,
            object_id__in=visible_profile_ids,
            archived=False,
        ).values_list("object_id", flat=True)
    )
    archived_pack_profile_count = CustomContentPackItem.objects.filter(
        pack=pack,
        content_type=profile_ct,
        object_id__in=all_profile_ids,
        archived=True,
    ).count()

    profiles = list(profiles_qs)
    for prof in profiles:
        prof.is_pack_scoped = prof.pk in pack_profile_object_ids
    profiles.sort(
        key=lambda prof: (
            2 if prof.is_pack_scoped else (0 if not prof.name else 1),
            prof.name or "",
        )
    )

    mods_by_profile = _pack_mods_for_target_ids(
        pack, ContentWeaponProfile, [prof.pk for prof in profiles]
    )
    display_profiles = [
        _PackModdedProfile(prof, mods_by_profile.get(prof.pk, [])) for prof in profiles
    ]

    context = {
        "pack": pack,
        "equipment": equipment,
        "profiles": display_profiles,
        "pack_profile_count": len(pack_profile_object_ids),
        "archived_pack_profile_count": archived_pack_profile_count,
        "back_url": _pack_url(pack),
    }
    assert_equivalent("core/pack/customise_weapon.html", context, request)
