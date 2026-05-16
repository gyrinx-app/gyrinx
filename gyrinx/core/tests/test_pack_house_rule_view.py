"""View-layer tests for the pack house-rule add/edit/delete flow.

Covers trait mods (weapon profile target) and special-rule mods (fighter
target), in addition to the previously-supported stat mods. The model-layer
behaviour is verified in ``content/tests/test_content_mod_application.py``;
these tests cover the form/view wiring.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from gyrinx.content.models import (
    ContentMod,
    ContentModApplication,
    ContentModFighterRule,
    ContentModFighterStat,
    ContentModStat,
    ContentModTrait,
    ContentRule,
    ContentWeaponTrait,
)
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


@pytest.fixture
def pack(user) -> CustomContentPack:
    return CustomContentPack.objects.create(name="HR Pack", owner=user)


@pytest.fixture
def weapon_profile(content_equipment_categories, make_equipment, make_weapon_profile):
    weapon = make_equipment(name="HR Test Gun", category="Special Weapons")
    profile = make_weapon_profile(
        equipment=weapon,
        name="",
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
    return profile


@pytest.fixture
def trait_knockback():
    return ContentWeaponTrait.objects.create(name="Knockback")


@pytest.fixture
def rule_fearless():
    return ContentRule.objects.create(name="Fearless")


@pytest.fixture
def content_stat_movement():
    """Ensure the form's dynamic fighter-stat choices include movement.

    Data migrations populate ``ContentStat`` rows in production but pytest
    runs with ``--nomigrations`` (``conftest`` / ``pyproject``) so we
    explicitly seed the row needed by the form here.
    """
    from gyrinx.content.models.statline import ContentStat

    stat, _ = ContentStat.objects.get_or_create(
        field_name="movement",
        defaults={"full_name": "Movement", "short_name": "M"},
    )
    return stat


def _login(client, user):
    client.force_login(user)


def _add_url(pack, target_type, target_id):
    return (
        reverse("core:pack-house-rule-add", args=(pack.id,))
        + f"?target_type={target_type}&target_id={target_id}"
    )


def _edit_url(pack, item_id):
    return reverse("core:pack-house-rule-edit", args=(pack.id, item_id))


# ---------------------------------------------------------------------------
# Trait mods (weapon profile target)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_trait_house_rule_creates_trait_mod_application(
    client, user, pack, weapon_profile, trait_knockback
):
    _login(client, user)
    url = _add_url(pack, "weapon-profile", weapon_profile.id)
    response = client.post(
        url,
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "mod_kind": "trait",
            "trait": str(trait_knockback.id),
            "mode": "add",
            # Stat fields left blank — should be ignored for trait kind.
            "stat": "",
            "value": "",
        },
    )
    assert response.status_code == 302, response.content

    [application] = ContentModApplication.objects.all_content()
    modifier = ContentMod.objects.get(pk=application.modifier_id)
    assert isinstance(modifier, ContentModTrait)
    assert modifier.trait_id == trait_knockback.id
    assert modifier.mode == "add"
    assert application.target_object_id == weapon_profile.id

    # The pack item linking the application must exist.
    assert CustomContentPackItem.objects.filter(
        pack=pack, object_id=application.id, archived=False
    ).exists()


@pytest.mark.django_db
def test_trait_kind_rejected_for_fighter_target(
    client, user, pack, content_fighter, trait_knockback
):
    """Form should reject a trait kind whose target isn't a weapon profile."""
    _login(client, user)
    url = _add_url(pack, "fighter", content_fighter.id)
    response = client.post(
        url,
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "mod_kind": "trait",
            "trait": str(trait_knockback.id),
            "mode": "add",
        },
    )
    # Form re-rendered (no redirect) because mod_kind is invalid for target.
    assert response.status_code == 200
    assert ContentModApplication.objects.count() == 0


# ---------------------------------------------------------------------------
# Rule mods (fighter target)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_rule_house_rule_creates_fighter_rule_mod_application(
    client, user, pack, content_fighter, rule_fearless
):
    _login(client, user)
    url = _add_url(pack, "fighter", content_fighter.id)
    response = client.post(
        url,
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "mod_kind": "rule",
            "rule": str(rule_fearless.id),
            "mode": "add",
        },
    )
    assert response.status_code == 302, response.content

    [application] = ContentModApplication.objects.all_content()
    modifier = ContentMod.objects.get(pk=application.modifier_id)
    assert isinstance(modifier, ContentModFighterRule)
    assert modifier.rule_id == rule_fearless.id
    assert modifier.mode == "add"
    assert application.target_object_id == content_fighter.id


@pytest.mark.django_db
def test_rule_kind_rejected_for_weapon_target(
    client, user, pack, weapon_profile, rule_fearless
):
    _login(client, user)
    url = _add_url(pack, "weapon-profile", weapon_profile.id)
    response = client.post(
        url,
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "mod_kind": "rule",
            "rule": str(rule_fearless.id),
            "mode": "add",
        },
    )
    assert response.status_code == 200
    assert ContentModApplication.objects.count() == 0


# ---------------------------------------------------------------------------
# Stat mods (regression — pre-existing behaviour must still work)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_weapon_stat_house_rule_still_works(client, user, pack, weapon_profile):
    _login(client, user)
    url = _add_url(pack, "weapon-profile", weapon_profile.id)
    response = client.post(
        url,
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "mod_kind": "stat",
            "stat": "damage",
            "mode": "set",
            "value": "1",
        },
    )
    assert response.status_code == 302, response.content
    [application] = ContentModApplication.objects.all_content()
    modifier = ContentMod.objects.get(pk=application.modifier_id)
    assert isinstance(modifier, ContentModStat)
    assert modifier.stat == "damage"
    assert modifier.value == "1"


@pytest.mark.django_db
def test_add_fighter_stat_house_rule_still_works(
    client, user, pack, content_fighter, content_stat_movement
):
    _login(client, user)
    url = _add_url(pack, "fighter", content_fighter.id)
    response = client.post(
        url,
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "mod_kind": "stat",
            "stat": "movement",
            "mode": "improve",
            "value": "1",
        },
    )
    assert response.status_code == 302, response.content
    [application] = ContentModApplication.objects.all_content()
    modifier = ContentMod.objects.get(pk=application.modifier_id)
    assert isinstance(modifier, ContentModFighterStat)


# ---------------------------------------------------------------------------
# Edit flow — switching between mod kinds recreates the modifier
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_edit_house_rule_switch_stat_to_trait(
    client, user, pack, weapon_profile, trait_knockback
):
    _login(client, user)
    # Create a stat house rule first.
    client.post(
        _add_url(pack, "weapon-profile", weapon_profile.id),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "mod_kind": "stat",
            "stat": "damage",
            "mode": "set",
            "value": "1",
        },
    )
    item = CustomContentPackItem.objects.get(pack=pack, archived=False)
    application = ContentModApplication.objects.all_content().get(pk=item.object_id)
    original_modifier_id = application.modifier_id

    # Now edit it to be a trait mod instead.
    response = client.post(
        _edit_url(pack, item.id),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "mod_kind": "trait",
            "trait": str(trait_knockback.id),
            "mode": "add",
        },
    )
    assert response.status_code == 302, response.content

    application.refresh_from_db()
    new_modifier = ContentMod.objects.get(pk=application.modifier_id)
    assert isinstance(new_modifier, ContentModTrait)
    assert new_modifier.trait_id == trait_knockback.id
    # Old modifier was deleted as part of the kind switch.
    assert not ContentMod.objects.filter(pk=original_modifier_id).exists()


@pytest.mark.django_db
def test_edit_trait_house_rule_in_place(
    client, user, pack, weapon_profile, trait_knockback
):
    _login(client, user)
    other_trait = ContentWeaponTrait.objects.create(name="Rapid Fire")
    client.post(
        _add_url(pack, "weapon-profile", weapon_profile.id),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "mod_kind": "trait",
            "trait": str(trait_knockback.id),
            "mode": "add",
        },
    )
    item = CustomContentPackItem.objects.get(pack=pack, archived=False)
    application = ContentModApplication.objects.all_content().get(pk=item.object_id)
    modifier_id = application.modifier_id

    # Update: change trait + mode, same kind.
    response = client.post(
        _edit_url(pack, item.id),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "mod_kind": "trait",
            "trait": str(other_trait.id),
            "mode": "remove",
        },
    )
    assert response.status_code == 302, response.content

    # Same modifier row mutated in place — same PK preserved.
    modifier = ContentMod.objects.get(pk=modifier_id)
    assert isinstance(modifier, ContentModTrait)
    assert modifier.trait_id == other_trait.id
    assert modifier.mode == "remove"


# ---------------------------------------------------------------------------
# Form validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_trait_kind_requires_trait_selection(client, user, pack, weapon_profile):
    _login(client, user)
    response = client.post(
        _add_url(pack, "weapon-profile", weapon_profile.id),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "mod_kind": "trait",
            "trait": "",
            "mode": "add",
        },
    )
    assert response.status_code == 200
    assert ContentModApplication.objects.count() == 0


@pytest.mark.django_db
def test_rule_kind_requires_rule_selection(client, user, pack, content_fighter):
    _login(client, user)
    response = client.post(
        _add_url(pack, "fighter", content_fighter.id),
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "mod_kind": "rule",
            "rule": "",
            "mode": "add",
        },
    )
    assert response.status_code == 200
    assert ContentModApplication.objects.count() == 0
