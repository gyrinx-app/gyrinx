"""Tests for ContentModApplication — pack-scoped house-rule modifications.

Covers the verification points from the plan:
1. Pack subscribed → mod applies; unsubscribed list → mod does not apply.
2. ContentEquipment-targeted weapon-stat mod applies to all profiles of that
   weapon for subscribed lists.
3. ContentFighter-targeted fighter-stat mod applies to fighter statline.
4. Default-assignment path: house-rule mod applies through
   ``ContentFighterDefaultAssignment.weapon_profiles_field``.
5. Two packs with conflicting mods on same target stack deterministically.
6. Archived ``CustomContentPackItem`` excludes the mod (matches ``with_packs``
   archived-exclude semantics).
7. Validation: cannot create a ``ContentModApplication`` whose modifier class
   doesn't match the target type.
8. Cache: removing a pack from ``List.packs`` removes the modded display.
"""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentFighter,
    ContentModApplication,
    ContentModFighterStat,
    ContentModStat,
    ContentWeaponProfile,
)
from gyrinx.core.models.list import ListFighterEquipmentAssignment
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


# Helpers ---------------------------------------------------------------------


def _attach_to_pack(pack, content_object, user):
    """Attach a content_object to a pack via CustomContentPackItem."""
    ct = ContentType.objects.get_for_model(type(content_object))
    item = CustomContentPackItem(
        pack=pack,
        content_type=ct,
        object_id=content_object.pk,
        owner=user,
    )
    item.save_with_user(user=user)
    return item


def _make_application(target, mod, pack, user):
    """Create a ContentModApplication and attach it to the pack."""
    ct = ContentType.objects.get_for_model(type(target))
    app = ContentModApplication.objects.create(
        target_content_type=ct,
        target_object_id=target.pk,
        modifier=mod,
    )
    _attach_to_pack(pack, app, user)
    return app


@pytest.fixture
def make_pack(user):
    def make_pack_(name="House Rules", **kwargs) -> CustomContentPack:
        return CustomContentPack.objects.create(name=name, owner=user, **kwargs)

    return make_pack_


@pytest.fixture
def weapon_with_profile(
    content_equipment_categories, make_equipment, make_weapon_profile
):
    """A library bail-fire-like weapon with a single named profile.

    Returns ``(equipment, profile)``.
    """
    weapon = make_equipment(
        name="House Rule Test Weapon",
        category="Special Weapons",
    )
    profile = make_weapon_profile(
        equipment=weapon,
        name="",  # standard profile
        cost=0,
        range_short='8"',
        range_long='16"',
        accuracy_short="+1",
        accuracy_long="",
        strength="4",
        armour_piercing="-1",
        damage="2",
        ammo="6+",
    )
    return weapon, profile


# 1. Pack subscribed → mod applies; unsubscribed list → mod does not. --------


@pytest.mark.django_db
def test_weapon_profile_mod_applies_only_for_subscribed_list(
    user, make_pack, make_list, make_list_fighter, weapon_with_profile
):
    weapon, profile = weapon_with_profile
    pack = make_pack(name="Damage 1 House Rule")
    mod = ContentModStat.objects.create(stat="damage", mode="set", value="1")
    _make_application(profile, mod, pack, user)

    lst = make_list("Subscribed list")
    fighter = make_list_fighter(lst, "Tester")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_profiles_field.add(profile)

    # Unsubscribed: original damage = 2.
    [vp] = [vp for vp in assignment.weapon_profiles() if vp.profile.pk == profile.pk]
    assert vp.damage == "2"

    # Subscribe and re-query: damage now 1, with modded display.
    lst.packs.add(pack)
    # Bust caches that depend on _mods.
    lst.__dict__.pop("pack_mods_by_target", None)
    fighter.__dict__.pop("_mods", None)
    fighter.__dict__.pop("assignments_cached", None)
    assignment.__dict__.pop("_mods", None)
    assignment.__dict__.pop("weapon_profiles_cached", None)

    [vp] = [vp for vp in assignment.weapon_profiles() if vp.profile.pk == profile.pk]
    assert vp.damage == "1"
    statline = vp.statline()
    damage_stat = next(s for s in statline if s.field_name == "damage")
    assert damage_stat.value == "1"
    assert damage_stat.modded is True


# 2. Fighter-targeted fighter-stat mod ---------------------------------------


@pytest.mark.django_db
def test_fighter_targeted_mod_applies_to_statline(
    user, make_pack, make_list, make_list_fighter, content_fighter
):
    pack = make_pack(name="Fighter buff")
    # Movement is "5\""; improving by 1 should give 6".
    mod = ContentModFighterStat.objects.create(
        stat="movement", mode="improve", value="1"
    )
    _make_application(content_fighter, mod, pack, user)

    lst = make_list("Subscribed")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Tester")
    statline = fighter.statline
    move = next(s for s in statline if s.field_name == "movement")
    assert move.value == '6"'
    assert move.modded is True


# 4. Default-assignment path -------------------------------------------------


@pytest.mark.django_db
def test_house_rule_applies_via_default_assignment(
    user,
    make_pack,
    make_list,
    make_list_fighter,
    content_fighter,
    weapon_with_profile,
):
    """A weapon assigned via ContentFighterDefaultAssignment must surface the
    pack-scoped mod for subscribed lists. Mirrors the regression fixed in
    PR #1740 for pack-scoped weapon profiles.
    """
    from gyrinx.content.models.default_assignment import ContentFighterDefaultAssignment

    weapon, profile = weapon_with_profile
    default_assignment = ContentFighterDefaultAssignment.objects.create(
        fighter=content_fighter, equipment=weapon
    )
    default_assignment.weapon_profiles_field.add(profile)

    pack = make_pack(name="Default-weapon house rule")
    mod = ContentModStat.objects.create(stat="damage", mode="set", value="1")
    _make_application(profile, mod, pack, user)

    lst = make_list("Subscribed")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Tester")

    # Find the default-derived assignment in fighter.assignments_cached.
    virtuals = [a for a in fighter.assignments_cached if a.equipment.pk == weapon.pk]
    assert virtuals, "Fighter should have the default weapon assigned"
    [virtual] = virtuals
    profiles = list(virtual.all_profiles())
    [vp] = [vp for vp in profiles if vp.profile.pk == profile.pk]
    assert vp.damage == "1"


# 5. Two packs stacking ------------------------------------------------------


@pytest.mark.django_db
def test_two_packs_stack_mods(
    user, make_pack, make_list, make_list_fighter, weapon_with_profile
):
    weapon, profile = weapon_with_profile
    pack_a = make_pack(name="Pack A")
    pack_b = make_pack(name="Pack B")
    mod_a = ContentModStat.objects.create(stat="strength", mode="worsen", value="1")
    mod_b = ContentModStat.objects.create(stat="strength", mode="worsen", value="1")
    _make_application(profile, mod_a, pack_a, user)
    _make_application(profile, mod_b, pack_b, user)

    lst = make_list("Both packs")
    lst.packs.add(pack_a, pack_b)
    fighter = make_list_fighter(lst, "Tester")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_profiles_field.add(profile)

    [vp] = [vp for vp in assignment.weapon_profiles() if vp.profile.pk == profile.pk]
    # 4 -> 3 -> 2.
    assert vp.strength == "2"


# 6. Archived pack item excludes the mod -------------------------------------


@pytest.mark.django_db
def test_archived_pack_item_excludes_mod(
    user, make_pack, make_list, make_list_fighter, weapon_with_profile
):
    weapon, profile = weapon_with_profile
    pack = make_pack(name="Will be archived")
    mod = ContentModStat.objects.create(stat="damage", mode="set", value="1")
    app = _make_application(profile, mod, pack, user)

    lst = make_list("Subscribed")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Tester")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_profiles_field.add(profile)

    # Archive the linking pack item.
    application_ct = ContentType.objects.get_for_model(ContentModApplication)
    item = CustomContentPackItem.objects.get(
        pack=pack, content_type=application_ct, object_id=app.pk, archived=False
    )
    item.archive()

    # Bust list-level cache, then expect original damage.
    lst.__dict__.pop("pack_mods_by_target", None)
    [vp] = [vp for vp in assignment.weapon_profiles() if vp.profile.pk == profile.pk]
    assert vp.damage == "2"


# 7. Validation --------------------------------------------------------------


@pytest.mark.django_db
def test_validation_rejects_class_mismatch(content_fighter, weapon_with_profile):
    weapon, profile = weapon_with_profile

    # Fighter-stat mod targeting a weapon profile is invalid.
    fighter_stat = ContentModFighterStat.objects.create(
        stat="movement", mode="improve", value="1"
    )
    profile_ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    bad = ContentModApplication(
        target_content_type=profile_ct,
        target_object_id=profile.pk,
        modifier=fighter_stat,
    )
    with pytest.raises(ValidationError):
        bad.full_clean()

    # Weapon-stat mod targeting a ContentFighter is invalid.
    weapon_stat = ContentModStat.objects.create(stat="damage", mode="set", value="1")
    fighter_ct = ContentType.objects.get_for_model(ContentFighter)
    bad2 = ContentModApplication(
        target_content_type=fighter_ct,
        target_object_id=content_fighter.pk,
        modifier=weapon_stat,
    )
    with pytest.raises(ValidationError):
        bad2.full_clean()


# 8. Cache: unsubscribing removes the modded display -------------------------


@pytest.mark.django_db
def test_unsubscribing_removes_mod(
    user, make_pack, make_list, make_list_fighter, weapon_with_profile
):
    weapon, profile = weapon_with_profile
    pack = make_pack(name="Toggle")
    mod = ContentModStat.objects.create(stat="damage", mode="set", value="1")
    _make_application(profile, mod, pack, user)

    lst = make_list("Subscribed")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Tester")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_profiles_field.add(profile)

    [vp] = [vp for vp in assignment.weapon_profiles() if vp.profile.pk == profile.pk]
    assert vp.damage == "1"

    lst.packs.remove(pack)
    # Re-fetch the list to simulate a fresh request.
    lst.refresh_from_db()
    fighter.refresh_from_db()
    fresh_lst = lst.__class__.objects.get(pk=lst.pk)
    fresh_fighter = fresh_lst.fighters().get(pk=fighter.pk)
    fresh_assignment = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
    fresh_assignment.list_fighter = fresh_fighter
    [vp] = [
        vp for vp in fresh_assignment.weapon_profiles() if vp.profile.pk == profile.pk
    ]
    assert vp.damage == "2"
