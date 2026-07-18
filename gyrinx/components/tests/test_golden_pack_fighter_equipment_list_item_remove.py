"""Golden-equivalence test for the pack fighter equipment-list item remove page."""

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
from gyrinx.content.models.weapon import ContentWeaponProfile
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _seed(user, make_content_fighter, content_house):
    pack = CustomContentPack.objects.create(
        name="Test Pack",
        summary="A test pack",
        listed=True,
        owner=user,
    )
    content_fighter = make_content_fighter("Pack Fighter", "ganger", content_house, 50)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(content_fighter),
        object_id=content_fighter.pk,
        owner=user,
    )
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Weapons", defaults={"group": "Weapons & Ammo"}
    )
    weapon = ContentEquipment.objects.create(
        name="Autogun", category=category, cost="15"
    )
    return pack, pack_item, content_fighter, weapon


@pytest.mark.django_db
def test_pack_fighter_equipment_list_item_remove_matches_legacy(
    user, make_content_fighter, content_house
):
    pack, pack_item, content_fighter, weapon = _seed(
        user, make_content_fighter, content_house
    )
    # Base weapon entry (no profile).
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=weapon, cost=0
    )
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": content_fighter,
        "eli": eli,
        "sibling_profiles": [],
    }
    assert_equivalent(
        "core/pack/pack_fighter_equipment_list_item_remove.html",
        context,
        _request(user),
    )


@pytest.mark.django_db
def test_pack_fighter_equipment_list_item_remove_with_siblings_matches_legacy(
    user, make_content_fighter, content_house
):
    pack, pack_item, content_fighter, weapon = _seed(
        user, make_content_fighter, content_house
    )
    # Base weapon entry (no profile) being removed.
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=weapon, cost=0
    )
    # A named profile whose equipment-list entry is a sibling.
    profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Focused beam",
        range_short="12",
        range_long="24",
        accuracy_short="+1",
        accuracy_long="-",
        strength="4",
        armour_piercing="-1",
        damage="2",
        ammo="4+",
        cost=5,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=weapon, weapon_profile=profile, cost=5
    )
    # Replicate the view's GET-branch sibling_profiles computation.
    sibling_profiles = list(
        ContentFighterEquipmentListItem.objects.filter(
            fighter=content_fighter,
            equipment=eli.equipment,
        )
        .exclude(pk=eli.pk)
        .select_related("equipment", "weapon_profile")
    )
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": content_fighter,
        "eli": eli,
        "sibling_profiles": sibling_profiles,
    }
    assert_equivalent(
        "core/pack/pack_fighter_equipment_list_item_remove.html",
        context,
        _request(user),
    )


@pytest.mark.django_db
def test_pack_fighter_equipment_list_item_remove_profile_entry_matches_legacy(
    user, make_content_fighter, content_house
):
    """Removing a profile-specific entry exercises the eli.weapon_profile branch."""
    pack, pack_item, content_fighter, weapon = _seed(
        user, make_content_fighter, content_house
    )
    profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Focused beam",
        range_short="12",
        range_long="24",
        accuracy_short="+1",
        accuracy_long="-",
        strength="4",
        armour_piercing="-1",
        damage="2",
        ammo="4+",
        cost=5,
    )
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=weapon, weapon_profile=profile, cost=5
    )
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": content_fighter,
        "eli": eli,
        "sibling_profiles": [],
    }
    assert_equivalent(
        "core/pack/pack_fighter_equipment_list_item_remove.html",
        context,
        _request(user),
    )
