"""Phase 7 of the cost-pinning programme (#1826): acquisition writes pins.

`pin_assignment` is the resolve-and-pin choke point every acquisition path
calls. These tests prove, per price source, that it writes the receipt live
resolution would agree with — amount + attribution FK + state — that the
§4.2 anchors stay unpinned, that pinning is value-neutral (cost_int() is
identical before and after), and that a receipt, once written, is never
overwritten by a later call.
"""

import pytest

from gyrinx.content.models import (
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentListExpansionRuleByHouse,
    ContentEquipmentUpgrade,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
    ContentWeaponAccessory,
)
from gyrinx.core.cost.pinning import pin_assignment
from gyrinx.core.models.list import (
    ListFighterEquipmentAssignment,
    PinState,
)
from gyrinx.core.tests.test_balance_sheet import fresh


@pytest.fixture
def ctx(user, make_list, make_list_fighter, make_equipment, make_weapon_profile):
    lst = make_list("Pinning Gang")
    fighter = make_list_fighter(lst, "Bob")
    equipment = make_equipment("Lasgun", cost=15)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=equipment
    )
    return {
        "lst": lst,
        "fighter": fighter,
        "equipment": equipment,
        "assignment": assignment,
        "make_weapon_profile": make_weapon_profile,
    }


def _base_pin(assignment):
    a = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
    return (
        a.pinned_base_amount,
        a.pinned_base_state,
        a.pinned_equipment_list_item_id,
        a.pinned_expansion_item_id,
    )


# --- Base provenance ---------------------------------------------------------


@pytest.mark.django_db
def test_catalog_base_pins_catalog(ctx):
    pin_assignment(ctx["assignment"])
    amount, state, cfeli_id, exp_id = _base_pin(ctx["assignment"])
    assert (amount, state) == (15, PinState.CATALOG)
    assert cfeli_id is None and exp_id is None


@pytest.mark.django_db
def test_equipment_list_discount_pins_source(ctx):
    item = ContentFighterEquipmentListItem.objects.create(
        fighter=ctx["fighter"].content_fighter, equipment=ctx["equipment"], cost=5
    )
    pin_assignment(ctx["assignment"])
    amount, state, cfeli_id, exp_id = _base_pin(ctx["assignment"])
    assert (amount, state, cfeli_id) == (5, PinState.SOURCE, item.pk)
    assert exp_id is None


@pytest.mark.django_db
def test_expansion_price_pins_source_and_outranks_list_item(ctx):
    """Expansions outrank equipment-list rows in live resolution; the
    receipt must attribute to the same winner."""
    ContentFighterEquipmentListItem.objects.create(
        fighter=ctx["fighter"].content_fighter, equipment=ctx["equipment"], cost=5
    )
    rule = ContentEquipmentListExpansionRuleByHouse.objects.create(
        house=ctx["lst"].content_house
    )
    expansion = ContentEquipmentListExpansion.objects.create(name="Pin Expansion")
    expansion.rules.add(rule)
    exp_item = ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion, equipment=ctx["equipment"], cost=4
    )
    assert fresh(ctx["assignment"]).base_cost_int() == 4  # expansion wins live

    pin_assignment(ctx["assignment"])
    amount, state, cfeli_id, exp_id = _base_pin(ctx["assignment"])
    assert (amount, state, exp_id) == (4, PinState.SOURCE, exp_item.pk)
    assert cfeli_id is None


@pytest.mark.django_db
def test_legacy_fighter_discount_preferred(ctx, make_content_fighter, content_house):
    """When base and legacy fighters both price the item, resolution prefers
    the legacy row — so must the receipt."""
    legacy_cf = make_content_fighter(
        type="Legacy Digger", category="GANGER", house=content_house, base_cost=40
    )
    ctx["fighter"].legacy_content_fighter = legacy_cf
    ctx["fighter"].save()
    ContentFighterEquipmentListItem.objects.create(
        fighter=ctx["fighter"].content_fighter, equipment=ctx["equipment"], cost=9
    )
    legacy_item = ContentFighterEquipmentListItem.objects.create(
        fighter=legacy_cf, equipment=ctx["equipment"], cost=6
    )
    pin_assignment(ctx["assignment"])
    amount, state, cfeli_id, _ = _base_pin(ctx["assignment"])
    assert (amount, state, cfeli_id) == (6, PinState.SOURCE, legacy_item.pk)


# --- Component provenance ------------------------------------------------------


@pytest.mark.django_db
def test_profile_rows_pin_catalog_and_source(ctx):
    catalog_profile = ctx["make_weapon_profile"](
        ctx["equipment"], name="Hotshot", cost=10
    )
    priced_profile = ctx["make_weapon_profile"](
        ctx["equipment"], name="Longshot", cost=12
    )
    item = ContentFighterEquipmentListItem.objects.create(
        fighter=ctx["fighter"].content_fighter,
        equipment=ctx["equipment"],
        weapon_profile=priced_profile,
        cost=7,
    )
    ctx["assignment"].weapon_profiles_field.add(catalog_profile, priced_profile)

    pin_assignment(ctx["assignment"])

    rows = {r.contentweaponprofile_id: r for r in ctx["assignment"].profile_rows.all()}
    assert (
        rows[catalog_profile.pk].pinned_amount,
        rows[catalog_profile.pk].pin_state,
    ) == (10, PinState.CATALOG)
    assert (
        rows[priced_profile.pk].pinned_amount,
        rows[priced_profile.pk].pin_state,
        rows[priced_profile.pk].pinned_equipment_list_item_id,
    ) == (7, PinState.SOURCE, item.pk)


@pytest.mark.django_db
def test_accessory_rows_pin_catalog_source_and_derived(ctx):
    flat = ContentWeaponAccessory.objects.create(name="Flat Scope", cost=8)
    priced = ContentWeaponAccessory.objects.create(name="Priced Scope", cost=8)
    override = ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=ctx["fighter"].content_fighter, weapon_accessory=priced, cost=3
    )
    formula = ContentWeaponAccessory.objects.create(
        name="Percent Scope", cost=0, cost_expression="ceil(cost_int * 0.5 / 5) * 5"
    )
    ctx["assignment"].weapon_accessories_field.add(flat, priced, formula)

    pin_assignment(ctx["assignment"])

    rows = {
        r.contentweaponaccessory_id: r for r in ctx["assignment"].accessory_rows.all()
    }
    assert (rows[flat.pk].pinned_amount, rows[flat.pk].pin_state) == (
        8,
        PinState.CATALOG,
    )
    assert (
        rows[priced.pk].pinned_amount,
        rows[priced.pk].pin_state,
        rows[priced.pk].pinned_equipment_list_accessory_id,
    ) == (3, PinState.SOURCE, override.pk)
    # Formula evaluated against the just-pinned 15 base: ceil(15*0.5/5)*5.
    assert (rows[formula.pk].pinned_amount, rows[formula.pk].pin_state) == (
        10,
        PinState.DERIVED,
    )


@pytest.mark.django_db
def test_upgrade_rows_pin_multi_and_single(ctx, make_equipment):
    from gyrinx.content.models import ContentEquipment

    multi_equipment = make_equipment(
        "Multi Gun", cost=10, upgrade_mode=ContentEquipment.UpgradeMode.MULTI
    )
    multi_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=ctx["fighter"], content_equipment=multi_equipment
    )
    flat_upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=multi_equipment, name="Mag", cost=5
    )
    priced_upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=multi_equipment, name="Drum", cost=9
    )
    override = ContentFighterEquipmentListUpgrade.objects.create(
        fighter=ctx["fighter"].content_fighter, upgrade=priced_upgrade, cost=4
    )
    multi_assignment.upgrades_field.add(flat_upgrade, priced_upgrade)

    # SINGLE stack on the default-mode equipment: rung1 pins the cumulative,
    # including a per-rung override on rung 0.
    rung0 = ContentEquipmentUpgrade.objects.create(
        equipment=ctx["equipment"], name="Rung 0", position=0, cost=10
    )
    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=ctx["fighter"].content_fighter, upgrade=rung0, cost=6
    )
    rung1 = ContentEquipmentUpgrade.objects.create(
        equipment=ctx["equipment"], name="Rung 1", position=1, cost=20
    )
    ctx["assignment"].upgrades_field.add(rung1)

    pin_assignment(multi_assignment)
    pin_assignment(ctx["assignment"])

    multi_rows = {
        r.contentequipmentupgrade_id: r for r in multi_assignment.upgrade_rows.all()
    }
    assert (
        multi_rows[flat_upgrade.pk].pinned_amount,
        multi_rows[flat_upgrade.pk].pin_state,
    ) == (5, PinState.CATALOG)
    assert (
        multi_rows[priced_upgrade.pk].pinned_amount,
        multi_rows[priced_upgrade.pk].pin_state,
        multi_rows[priced_upgrade.pk].pinned_equipment_list_upgrade_id,
    ) == (4, PinState.SOURCE, override.pk)

    single_row = ctx["assignment"].upgrade_rows.get()
    # Cumulative with the rung-0 override applied: 6 + 20.
    assert (single_row.pinned_amount, single_row.pin_state) == (26, PinState.DERIVED)


# --- Anchors stay unpinned ------------------------------------------------------


@pytest.mark.django_db
def test_overridden_and_linked_bases_stay_unpinned(ctx, make_equipment):
    ListFighterEquipmentAssignment.objects.filter(pk=ctx["assignment"].pk).update(
        cost_override=3
    )
    pin_assignment(ctx["assignment"])
    assert _base_pin(ctx["assignment"])[1] == PinState.UNPINNED

    child = ListFighterEquipmentAssignment.objects.create(
        list_fighter=ctx["fighter"],
        content_equipment=make_equipment("Sidearm", cost=20),
        linked_equipment_parent=ctx["assignment"],
    )
    pin_assignment(child)
    assert _base_pin(child)[1] == PinState.UNPINNED


@pytest.mark.django_db
def test_default_kit_components_stay_unpinned(ctx, make_weapon_profile):
    """Default-kit components are free by membership — no receipt to write —
    while a non-kit component on the same assignment pins normally."""
    kit_profile = make_weapon_profile(ctx["equipment"], name="Kit Shot", cost=10)
    bought_profile = make_weapon_profile(ctx["equipment"], name="Extra Shot", cost=12)
    default = ContentFighterDefaultAssignment.objects.create(
        fighter=ctx["fighter"].content_fighter, equipment=ctx["equipment"]
    )
    default.weapon_profiles_field.add(kit_profile)
    ListFighterEquipmentAssignment.objects.filter(pk=ctx["assignment"].pk).update(
        from_default_assignment=default, cost_override=0
    )
    ctx["assignment"].weapon_profiles_field.add(kit_profile, bought_profile)

    pin_assignment(ctx["assignment"])

    rows = {r.contentweaponprofile_id: r for r in ctx["assignment"].profile_rows.all()}
    assert rows[kit_profile.pk].pin_state == PinState.UNPINNED
    assert rows[kit_profile.pk].pinned_amount is None
    assert (
        rows[bought_profile.pk].pinned_amount,
        rows[bought_profile.pk].pin_state,
    ) == (
        12,
        PinState.CATALOG,
    )


# --- Safety properties -----------------------------------------------------------


@pytest.mark.django_db
def test_pinning_is_value_neutral(ctx, make_weapon_profile):
    """cost_int() must be identical before and after pinning — the receipt
    records the price, it never changes it."""
    ContentFighterEquipmentListItem.objects.create(
        fighter=ctx["fighter"].content_fighter, equipment=ctx["equipment"], cost=5
    )
    profile = make_weapon_profile(ctx["equipment"], name="Hotshot", cost=10)
    accessory = ContentWeaponAccessory.objects.create(
        name="Percent Scope", cost=0, cost_expression="ceil(cost_int * 0.5 / 5) * 5"
    )
    ctx["assignment"].weapon_profiles_field.add(profile)
    ctx["assignment"].weapon_accessories_field.add(accessory)

    before = fresh(ctx["assignment"]).cost_int()
    pin_assignment(ctx["assignment"])
    after = fresh(ctx["assignment"]).cost_int()
    assert before == after


@pytest.mark.django_db
def test_receipts_are_never_overwritten(ctx):
    """A second call after a price change must not re-pin at the new price —
    corrections flow through sweeps, not through re-pinning."""
    item = ContentFighterEquipmentListItem.objects.create(
        fighter=ctx["fighter"].content_fighter, equipment=ctx["equipment"], cost=5
    )
    assert pin_assignment(ctx["assignment"]) == 1
    ContentFighterEquipmentListItem.objects.filter(pk=item.pk).update(cost=9)

    assert pin_assignment(ctx["assignment"]) == 0  # nothing left to pin
    assert _base_pin(ctx["assignment"])[0] == 5  # acquisition price stands
