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


def _add_url(pack, target_type, target_id, mod_kind="stat"):
    return (
        reverse("core:pack-house-rule-add", args=(pack.id,))
        + f"?target_type={target_type}&target_id={target_id}&mod_kind={mod_kind}"
    )


def _edit_url(pack, item_id, mod_kind=None):
    base = reverse("core:pack-house-rule-edit", args=(pack.id, item_id))
    if mod_kind:
        return f"{base}?mod_kind={mod_kind}"
    return base


# ---------------------------------------------------------------------------
# Trait mods (weapon profile target)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_trait_house_rule_creates_trait_mod_application(
    client, user, pack, weapon_profile, trait_knockback
):
    _login(client, user)
    url = _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="trait")
    response = client.post(
        url,
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "trait": str(trait_knockback.id),
            "mode": "add",
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
def test_trait_kind_in_url_coerced_for_fighter_target(
    client, user, pack, content_fighter, trait_knockback
):
    """A trait kind in the URL for a fighter target is silently coerced to
    the default kind (stat) — invalid kind/target combinations don't 404
    or accept the wrong mod type."""
    _login(client, user)
    url = _add_url(pack, "fighter", content_fighter.id, mod_kind="trait")
    response = client.get(url)
    # Page renders the default (stat) form, no trait fields.
    assert response.status_code == 200
    assert b'name="trait"' not in response.content
    assert ContentModApplication.objects.count() == 0


# ---------------------------------------------------------------------------
# Rule mods (fighter target)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_rule_house_rule_creates_fighter_rule_mod_application(
    client, user, pack, content_fighter, rule_fearless
):
    _login(client, user)
    url = _add_url(pack, "fighter", content_fighter.id, mod_kind="rule")
    response = client.post(
        url,
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
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
def test_rule_kind_in_url_coerced_for_weapon_target(
    client, user, pack, weapon_profile, rule_fearless
):
    """A rule kind in the URL for a weapon target is silently coerced to
    the default kind (stat)."""
    _login(client, user)
    url = _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="rule")
    response = client.get(url)
    assert response.status_code == 200
    assert b'name="rule"' not in response.content
    assert ContentModApplication.objects.count() == 0


# ---------------------------------------------------------------------------
# Stat mods (regression — pre-existing behaviour must still work)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_weapon_stat_house_rule_still_works(client, user, pack, weapon_profile):
    _login(client, user)
    url = _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="stat")
    response = client.post(
        url,
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
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
    url = _add_url(pack, "fighter", content_fighter.id, mod_kind="stat")
    response = client.post(
        url,
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "stat": "movement",
            "mode": "improve",
            "value": "1",
        },
    )
    assert response.status_code == 302, response.content
    [application] = ContentModApplication.objects.all_content()
    modifier = ContentMod.objects.get(pk=application.modifier_id)
    assert isinstance(modifier, ContentModFighterStat)


# Default kind on a target=stat URL with no mod_kind param renders the stat form.
@pytest.mark.django_db
def test_default_kind_is_stat_when_omitted_from_url(client, user, pack, weapon_profile):
    _login(client, user)
    url = (
        reverse("core:pack-house-rule-add", args=(pack.id,))
        + f"?target_type=weapon-profile&target_id={weapon_profile.id}"
    )
    response = client.get(url)
    assert response.status_code == 200
    # Stat fields visible; trait field absent.
    assert b'name="stat"' in response.content
    assert b'name="trait"' not in response.content


# URL drives kind: switching mod_kind in the URL renders the matching fields.
@pytest.mark.django_db
def test_url_mod_kind_drives_visible_fields(client, user, pack, weapon_profile):
    _login(client, user)
    url = _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="trait")
    response = client.get(url)
    assert response.status_code == 200
    assert b'name="trait"' in response.content
    assert b'name="stat"' not in response.content
    assert b'name="value"' not in response.content


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
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="stat"),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "stat": "damage",
            "mode": "set",
            "value": "1",
        },
    )
    item = CustomContentPackItem.objects.get(pack=pack, archived=False)
    application = ContentModApplication.objects.all_content().get(pk=item.object_id)
    original_modifier_id = application.modifier_id

    # Now edit it to be a trait mod instead — kind switch is a URL param.
    response = client.post(
        _edit_url(pack, item.id, mod_kind="trait"),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
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
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="trait"),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "trait": str(trait_knockback.id),
            "mode": "add",
        },
    )
    item = CustomContentPackItem.objects.get(pack=pack, archived=False)
    application = ContentModApplication.objects.all_content().get(pk=item.object_id)
    modifier_id = application.modifier_id

    # Update: change trait + mode, same kind (omitting kind in URL falls
    # back to the existing modifier's kind).
    response = client.post(
        _edit_url(pack, item.id),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
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


@pytest.mark.django_db
def test_edit_renders_existing_kind_when_no_url_override(
    client, user, pack, weapon_profile, trait_knockback
):
    """Visiting edit without ?mod_kind= shows the form for the existing
    modifier's kind, pre-populated."""
    _login(client, user)
    client.post(
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="trait"),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "trait": str(trait_knockback.id),
            "mode": "add",
        },
    )
    item = CustomContentPackItem.objects.get(pack=pack, archived=False)
    response = client.get(_edit_url(pack, item.id))
    assert response.status_code == 200
    assert b'name="trait"' in response.content
    assert b'name="stat"' not in response.content


# ---------------------------------------------------------------------------
# Form validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_trait_kind_requires_trait_selection(client, user, pack, weapon_profile):
    _login(client, user)
    response = client.post(
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="trait"),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "trait": "",
            "mode": "add",
        },
    )
    assert response.status_code == 200
    assert ContentModApplication.objects.count() == 0


# ---------------------------------------------------------------------------
# Pack-aware rule rendering on form + picker (fighter targets)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_form_renders_base_rules_on_fighter_target(
    client, user, pack, content_fighter, rule_fearless
):
    """Existing rules on the fighter show up on the form's target card."""
    content_fighter.rules.add(rule_fearless)
    _login(client, user)
    url = _add_url(pack, "fighter", content_fighter.id, mod_kind="stat")
    response = client.get(url)
    assert response.status_code == 200
    assert b"Fearless" in response.content


@pytest.mark.django_db
def test_form_renders_added_rule_with_tooltipped_underline(
    client, user, pack, content_fighter, rule_fearless
):
    _login(client, user)
    client.post(
        _add_url(pack, "fighter", content_fighter.id, mod_kind="rule"),
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "rule": str(rule_fearless.id),
            "mode": "add",
        },
    )
    response = client.get(
        _add_url(pack, "fighter", content_fighter.id, mod_kind="stat")
    )
    assert response.status_code == 200
    assert b"Fearless" in response.content
    assert b'class="tooltipped"' in response.content
    assert b"Added by this pack" in response.content


@pytest.mark.django_db
def test_form_renders_removed_rule_struck_through(
    client, user, pack, content_fighter, rule_fearless
):
    content_fighter.rules.add(rule_fearless)
    _login(client, user)
    client.post(
        _add_url(pack, "fighter", content_fighter.id, mod_kind="rule"),
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "rule": str(rule_fearless.id),
            "mode": "remove",
        },
    )
    response = client.get(
        _add_url(pack, "fighter", content_fighter.id, mod_kind="stat")
    )
    assert response.status_code == 200
    assert b"Fearless" in response.content
    assert b"text-decoration-line-through" in response.content
    assert b"Removed by this pack" in response.content


@pytest.mark.django_db
def test_picker_renders_fighter_rules_with_pack_mods(
    client, user, pack, content_fighter, rule_fearless
):
    """The fighter picker shows base rules and any pack-rule additions/
    removals on each row."""
    content_fighter.rules.add(rule_fearless)
    other = ContentRule.objects.create(name="Sprint")
    _login(client, user)
    # Add: Sprint.
    client.post(
        _add_url(pack, "fighter", content_fighter.id, mod_kind="rule"),
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "rule": str(other.id),
            "mode": "add",
        },
    )
    # Remove: Fearless.
    client.post(
        _add_url(pack, "fighter", content_fighter.id, mod_kind="rule"),
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "rule": str(rule_fearless.id),
            "mode": "remove",
        },
    )
    response = client.get(
        reverse("core:pack-house-rule-picker", args=(pack.id,)) + "?target_type=fighter"
    )
    assert response.status_code == 200
    body = response.content
    assert b"Fearless" in body
    assert b"Sprint" in body
    assert b"text-decoration-line-through" in body
    assert b'class="tooltipped"' in body


# ---------------------------------------------------------------------------
# Pack-aware trait rendering on form + picker
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_form_renders_base_traits_on_weapon_target(
    client, user, pack, weapon_profile, trait_knockback
):
    """Existing traits on the profile show up on the form's target card."""
    weapon_profile.traits.add(trait_knockback)
    _login(client, user)
    url = _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="stat")
    response = client.get(url)
    assert response.status_code == 200
    assert b"Knockback" in response.content


@pytest.mark.django_db
def test_form_renders_added_trait_as_badge_after_add_mod(
    client, user, pack, weapon_profile, trait_knockback
):
    """After adding an 'add' trait house rule, the trait appears as an
    'added' badge with a tooltip on the form card."""
    _login(client, user)
    # Create the trait house rule.
    client.post(
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="trait"),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "trait": str(trait_knockback.id),
            "mode": "add",
        },
    )
    # Now visit the form (any kind) and confirm the badge + tooltip render.
    response = client.get(
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="stat")
    )
    assert response.status_code == 200
    assert b"Knockback" in response.content
    # Added traits use the design-system ``tooltipped`` underline, not a badge.
    assert b'class="tooltipped"' in response.content
    assert b"Added by this pack" in response.content


@pytest.mark.django_db
def test_form_renders_removed_trait_struck_through(
    client, user, pack, weapon_profile, trait_knockback
):
    """A 'remove' trait house rule renders the base trait with line-through
    and a 'will be removed' tooltip."""
    weapon_profile.traits.add(trait_knockback)
    _login(client, user)
    client.post(
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="trait"),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "trait": str(trait_knockback.id),
            "mode": "remove",
        },
    )
    response = client.get(
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="stat")
    )
    assert response.status_code == 200
    assert b"Knockback" in response.content
    assert b"text-decoration-line-through" in response.content
    assert b"Removed by this pack" in response.content


@pytest.mark.django_db
def test_picker_renders_traits_with_pack_mods(
    client, user, pack, weapon_profile, trait_knockback
):
    """The weapon-profile picker shows base traits and any pack-rule
    additions/removals on each row."""
    weapon_profile.traits.add(trait_knockback)
    other = ContentWeaponTrait.objects.create(name="Rapid Fire")
    _login(client, user)
    # Add: Rapid Fire.
    client.post(
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="trait"),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "trait": str(other.id),
            "mode": "add",
        },
    )
    # Remove: Knockback.
    client.post(
        _add_url(pack, "weapon-profile", weapon_profile.id, mod_kind="trait"),
        {
            "target_type": "weapon-profile",
            "target_id": str(weapon_profile.id),
            "trait": str(trait_knockback.id),
            "mode": "remove",
        },
    )
    response = client.get(
        reverse("core:pack-house-rule-picker", args=(pack.id,))
        + "?target_type=weapon-profile"
    )
    assert response.status_code == 200
    body = response.content
    assert b"Knockback" in body
    assert b"Rapid Fire" in body
    assert b"text-decoration-line-through" in body
    assert b'class="tooltipped"' in body


@pytest.mark.django_db
def test_rule_kind_requires_rule_selection(client, user, pack, content_fighter):
    _login(client, user)
    response = client.post(
        _add_url(pack, "fighter", content_fighter.id, mod_kind="rule"),
        {
            "target_type": "fighter",
            "target_id": str(content_fighter.id),
            "rule": "",
            "mode": "add",
        },
    )
    assert response.status_code == 200
    assert ContentModApplication.objects.count() == 0
