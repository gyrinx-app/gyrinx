"""Tests for fighter mod pickers on pack-defined gear and weapons (issue #1753).

``EquipmentModifiersForm`` (driven by ``FighterModPickerMixin``) plumbs
``ContentModFighterStat`` / ``ContentModFighterRule`` / ``ContentModFighterSkill``
rows into ``ContentEquipment.modifiers`` from the Modifiers tab of the pack
gear/weapon editor. Once attached, the runtime path in
``ListFighterEquipmentAssignment._mods`` picks them up for subscribed lists.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
)
from gyrinx.content.models.metadata import ContentRule
from gyrinx.content.models.modifier import (
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentModFighterStat,
    ContentModSkillTreeAccess,
)
from gyrinx.content.models.skill import ContentSkill, ContentSkillCategory
from gyrinx.content.models.statline import ContentStat
from gyrinx.core.forms.pack import (
    ContentGearPackForm,
    ContentWeaponPackForm,
    EquipmentModifiersForm,
)
from gyrinx.core.models.list import ListFighterEquipmentAssignment
from gyrinx.core.models.pack import CustomContentPackItem


def _ct(model):
    return ContentType.objects.get_for_model(model)


def _add_to_pack(pack, obj):
    CustomContentPackItem.objects.create(
        pack=pack, content_type=_ct(type(obj)), object_id=obj.pk, owner=pack.owner
    )


@pytest.fixture(autouse=True)
def _seed_movement_stat(db):
    """Ensure the ``movement`` ContentStat exists and is linked to a Fighter
    statline type.

    Data migration 0148 seeds the canonical set in production, but pytest
    runs with ``--nomigrations`` so we materialise the rows the tests need
    on the fly. The picker filters stats by membership in a statline type,
    so the link is what makes ``movement`` visible to ``EquipmentModifiersForm``.
    """
    from gyrinx.content.models.statline import (
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


@pytest.fixture
def gear_category(db):
    return ContentEquipmentCategory.objects.create(
        name="Pack Gear Cat", group="Personal Equipment"
    )


@pytest.fixture
def weapon_category(db):
    return ContentEquipmentCategory.objects.create(
        name="Pack Pistols Cat", group="Weapons & Ammo"
    )


@pytest.fixture
def pack_gear(pack, gear_category):
    gear = ContentEquipment.objects.create(
        name="Pack Plate", category=gear_category, cost=10
    )
    _add_to_pack(pack, gear)
    return gear


@pytest.fixture
def pack_weapon(pack, weapon_category):
    weapon = ContentEquipment.objects.create(
        name="Pack Pistol", category=weapon_category, cost=20
    )
    _add_to_pack(pack, weapon)
    return weapon


# --- Form-level behaviour -----------------------------------------------------


@pytest.mark.django_db
def test_gear_and_weapon_forms_have_no_mod_fields():
    """The detail forms must NOT carry mod fields — those live on the
    Modifiers tab via ``EquipmentModifiersForm``."""
    gear_form = ContentGearPackForm()
    weapon_form = ContentWeaponPackForm()
    assert not any(name.startswith("fmod_") for name in gear_form.fields)
    assert not any(name.startswith("fmod_") for name in weapon_form.fields)


@pytest.mark.django_db
def test_modifiers_form_exposes_fighter_mod_fields(pack):
    form = EquipmentModifiersForm(pack=pack)
    movement = ContentStat.objects.get(field_name="movement")
    assert f"fmod_stat_{movement.field_name}_mode" in form.fields
    assert f"fmod_stat_{movement.field_name}_value" in form.fields


@pytest.mark.django_db
def test_modifiers_form_validates_stat_value_required(pack, pack_gear):
    movement = ContentStat.objects.get(field_name="movement")
    form = EquipmentModifiersForm(
        data={
            f"fmod_stat_{movement.field_name}_mode": "improve",
            f"fmod_stat_{movement.field_name}_value": "",
        },
        instance=pack_gear,
        pack=pack,
    )
    assert not form.is_valid()
    assert f"fmod_stat_{movement.field_name}_value" in form.errors


@pytest.mark.django_db
def test_modifiers_form_validates_integer_for_improve(pack, pack_gear):
    movement = ContentStat.objects.get(field_name="movement")
    form = EquipmentModifiersForm(
        data={
            f"fmod_stat_{movement.field_name}_mode": "improve",
            f"fmod_stat_{movement.field_name}_value": "not-an-int",
        },
        instance=pack_gear,
        pack=pack,
    )
    assert not form.is_valid()
    assert f"fmod_stat_{movement.field_name}_value" in form.errors


@pytest.mark.django_db
def test_modifiers_form_save_attaches_fighter_stat_mod(pack, pack_gear):
    movement = ContentStat.objects.get(field_name="movement")
    form = EquipmentModifiersForm(
        data={
            f"fmod_stat_{movement.field_name}_mode": "improve",
            f"fmod_stat_{movement.field_name}_value": "1",
        },
        instance=pack_gear,
        pack=pack,
    )
    assert form.is_valid(), form.errors
    obj = form.save()
    attached = list(obj.modifiers.all())
    assert len(attached) == 1
    mod = attached[0]
    assert isinstance(mod, ContentModFighterStat)
    assert mod.stat == movement.field_name
    assert mod.mode == "improve"
    assert mod.value == "1"


@pytest.mark.django_db
def test_modifiers_form_tolerates_preexisting_duplicate_mods(pack, pack_gear):
    """Regression for #1915: duplicate ContentModFighterStat rows in the library
    must not crash the modifiers form with MultipleObjectsReturned."""
    movement = ContentStat.objects.get(field_name="movement")
    for _ in range(3):
        ContentModFighterStat.objects.create(
            stat=movement.field_name, mode="improve", value="1"
        )

    form = EquipmentModifiersForm(
        data={
            f"fmod_stat_{movement.field_name}_mode": "improve",
            f"fmod_stat_{movement.field_name}_value": "1",
        },
        instance=pack_gear,
        pack=pack,
    )
    assert form.is_valid(), form.errors
    obj = form.save()

    dupes = ContentModFighterStat.objects.filter(
        stat=movement.field_name, mode="improve", value="1"
    ).order_by("pk")
    # Reuses an existing duplicate; no new row created.
    assert dupes.count() == 3
    attached = list(obj.modifiers.all())
    assert len(attached) == 1
    assert attached[0] == dupes.first()


@pytest.mark.django_db
def test_modifiers_form_save_attaches_rule_and_skill_mods(pack, pack_weapon):
    rule = ContentRule.objects.create(name="Pack Frenzy")
    _add_to_pack(pack, rule)
    cat = ContentSkillCategory.objects.create(name="Pack Combat")
    _add_to_pack(pack, cat)
    skill = ContentSkill.objects.create(name="Pack Parry", category=cat)
    _add_to_pack(pack, skill)

    form = EquipmentModifiersForm(
        data={
            f"fmod_rule_{rule.pk}": "add",
            f"fmod_skill_{skill.pk}": "add",
        },
        instance=pack_weapon,
        pack=pack,
    )
    assert form.is_valid(), form.errors
    obj = form.save()
    mods = list(obj.modifiers.all())
    assert len(mods) == 2
    assert any(
        isinstance(m, ContentModFighterRule)
        and m.rule_id == rule.pk
        and m.mode == "add"
        for m in mods
    )
    assert any(
        isinstance(m, ContentModFighterSkill)
        and m.skill_id == skill.pk
        and m.mode == "add"
        for m in mods
    )


@pytest.mark.django_db
def test_modifiers_form_initial_populates_from_existing_mods(pack, pack_gear):
    """Visiting the Modifiers tab pre-populates from existing modifiers."""
    movement = ContentStat.objects.get(field_name="movement")
    mod = ContentModFighterStat.objects.create(
        stat=movement.field_name, mode="improve", value="1"
    )
    pack_gear.modifiers.add(mod)

    form = EquipmentModifiersForm(instance=pack_gear, pack=pack)
    assert form.initial[f"fmod_stat_{movement.field_name}_mode"] == "improve"
    assert form.initial[f"fmod_stat_{movement.field_name}_value"] == "1"


@pytest.mark.django_db
def test_modifiers_form_save_preserves_unmanaged_mod_types(pack, pack_gear):
    """SkillTreeAccess mods set via admin survive a Modifiers-tab save."""
    cat = ContentSkillCategory.objects.create(name="Brawl Cat")
    sta = ContentModSkillTreeAccess.objects.create(
        skill_category=cat, mode="add_primary"
    )
    pack_gear.modifiers.add(sta)
    movement = ContentStat.objects.get(field_name="movement")

    form = EquipmentModifiersForm(
        data={
            f"fmod_stat_{movement.field_name}_mode": "improve",
            f"fmod_stat_{movement.field_name}_value": "1",
        },
        instance=pack_gear,
        pack=pack,
    )
    assert form.is_valid(), form.errors
    obj = form.save()
    mods = list(obj.modifiers.all())
    assert any(m.pk == sta.pk for m in mods)
    assert any(isinstance(m, ContentModFighterStat) for m in mods)


# --- View-level behaviour -----------------------------------------------------


@pytest.mark.django_db
def test_add_gear_view_does_not_render_mod_picker(client, user, pack):
    """The add view must NOT render the mod picker — that lives on the
    Modifiers tab post-creation."""
    client.force_login(user)
    url = reverse("core:pack-add-item", args=(pack.id, "gear"))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Fighter stat modifiers" not in response.content
    assert b"Fighter rule modifiers" not in response.content
    assert b"Fighter skill modifiers" not in response.content
    # The help text pointing at the Modifiers tab is shown.
    assert b"Modifiers tab" in response.content


@pytest.mark.django_db
def test_add_gear_view_creates_equipment_without_mods(
    client, user, pack, gear_category
):
    client.force_login(user)
    url = reverse("core:pack-add-item", args=(pack.id, "gear"))
    response = client.post(
        url,
        {
            "name": "Jump Boots",
            "category": str(gear_category.pk),
            "cost": "8",
            "rarity": "C",
            "rarity_roll": "",
        },
    )
    assert response.status_code == 302
    gear = ContentEquipment.objects.all_content().get(name="Jump Boots")
    assert list(gear.modifiers.all()) == []


@pytest.mark.django_db
def test_edit_gear_view_shows_tabs_and_no_mod_picker(client, user, pack, pack_gear):
    """The Details tab must show the Details/Modifiers tab nav and NOT the picker."""
    client.force_login(user)
    pack_item = CustomContentPackItem.objects.get(
        pack=pack, content_type=_ct(ContentEquipment), object_id=pack_gear.pk
    )
    response = client.get(reverse("core:pack-edit-item", args=(pack.id, pack_item.id)))
    assert response.status_code == 200
    assert b"Modifiers" in response.content  # tab label
    # The mod picker only appears on the Modifiers tab.
    assert b"Fighter stat modifiers" not in response.content


@pytest.mark.django_db
def test_modifiers_view_renders_picker_and_round_trips(client, user, pack, pack_gear):
    """The Modifiers tab GETs the picker, pre-populated with existing mods;
    POST swaps the mod and redirects back to the Modifiers tab."""
    client.force_login(user)
    movement = ContentStat.objects.get(field_name="movement")
    mod = ContentModFighterStat.objects.create(
        stat=movement.field_name, mode="improve", value="1"
    )
    pack_gear.modifiers.add(mod)

    pack_item = CustomContentPackItem.objects.get(
        pack=pack, content_type=_ct(ContentEquipment), object_id=pack_gear.pk
    )
    modifiers_url = reverse("core:pack-item-modifiers", args=(pack.id, pack_item.id))

    # GET — picker visible and existing mod pre-populated.
    response = client.get(modifiers_url)
    assert response.status_code == 200
    assert b"Fighter stat modifiers" in response.content
    assert b'value="improve" selected' in response.content

    # POST — swap to worsen movement -1.
    response = client.post(
        modifiers_url,
        {
            f"fmod_stat_{movement.field_name}_mode": "worsen",
            f"fmod_stat_{movement.field_name}_value": "1",
        },
    )
    assert response.status_code == 302
    assert response["Location"] == modifiers_url
    mods = list(pack_gear.modifiers.all())
    assert len(mods) == 1
    assert isinstance(mods[0], ContentModFighterStat)
    assert mods[0].mode == "worsen"


@pytest.mark.django_db
def test_modifiers_view_404s_for_non_equipment(client, user, pack):
    """Only gear and weapons have a Modifiers tab. Other pack-item types 404."""
    client.force_login(user)
    rule = ContentRule.objects.create(name="Standalone Rule")
    _add_to_pack(pack, rule)
    item = CustomContentPackItem.objects.get(
        pack=pack, content_type=_ct(ContentRule), object_id=rule.pk
    )
    response = client.get(reverse("core:pack-item-modifiers", args=(pack.id, item.id)))
    assert response.status_code == 404


# --- Subscriber runtime application ------------------------------------------


@pytest.mark.django_db
def test_subscriber_gets_pack_equipment_stat_mod(
    user, make_list, make_list_fighter, pack, pack_gear
):
    """A subscribed list's fighter equipped with the pack gear sees the mod."""
    movement = ContentStat.objects.get(field_name="movement")
    mod = ContentModFighterStat.objects.create(
        stat=movement.field_name, mode="improve", value="2"
    )
    pack_gear.modifiers.add(mod)

    lst = make_list("Sub Test")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Subbed Fighter")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=pack_gear
    )
    assert mod in assignment._mods
