"""Golden-equivalence test for the pack fighter "add default weapon" page."""

from __future__ import annotations

from collections import defaultdict

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_fighter_default_weapons_add_matches_legacy(
    user, content_house, make_content_fighter
):
    from gyrinx.content.models.equipment import (
        ContentEquipment,
        ContentEquipmentCategory,
    )
    from gyrinx.content.models.weapon import ContentWeaponProfile, ContentWeaponTrait
    from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
    from gyrinx.core.views.pack import _build_default_equipment_choices

    pack = CustomContentPack.objects.create(
        name="Test Pack", summary="A test pack", listed=True, owner=user
    )
    fighter = make_content_fighter("Pack Fighter", "ganger", content_house, 50)
    ct = ContentType.objects.get_for_model(fighter)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=fighter.pk, owner=user
    )

    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Basic Weapons", defaults={"group": "Weapons & Ammo"}
    )
    weapon = ContentEquipment.objects.create(
        name="Combi-weapon", category=category, cost="35"
    )
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="",
        range_short="8",
        range_long="24",
        accuracy_short="+1",
        accuracy_long="-",
        strength="3",
        armour_piercing="-",
        damage="1",
        ammo="4+",
        cost=0,
    )
    grenade = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Grenade Launcher",
        range_short="6",
        range_long="24",
        accuracy_short="-1",
        accuracy_long="-",
        strength="6",
        armour_piercing="-2",
        damage="2",
        ammo="6+",
        cost=15,
    )
    grenade.traits.set([ContentWeaponTrait.objects.create(name="Knockback")])

    # Replicate the view's GET-branch context construction exactly.
    equipment = _build_default_equipment_choices(pack, is_weapon=True)
    categories = defaultdict(list)
    for item in equipment:
        profiles = list(item.contentweaponprofile_set.all())
        standard = [p for p in profiles if p.cost == 0]
        non_standard = [p for p in profiles if p.cost > 0]
        categories[item.category.name].append(
            {
                "equipment": item,
                "standard_profiles": standard,
                "non_standard_profiles": non_standard,
                "all_profiles": profiles,
            }
        )

    request = _request(user)
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": fighter,
        "categories": dict(categories),
        "search_q": "",
        "error_message": None,
    }
    assert_equivalent(
        "core/pack/pack_fighter_default_weapons_add.html", context, request
    )
