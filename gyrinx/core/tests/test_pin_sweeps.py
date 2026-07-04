"""Phase 6 of the cost-pinning programme (#1826): sweeps reach pinned rows.

The legacy cost-change sweeps find affected assignments through their live
context: the holder's content fighter, or the equipment currently referenced
by the changed row. Pinned gear breaks that assumption — a pin is an FK to
the price-setting content object, and the row carrying it may since have
moved to a holder (or drifted from an equipment context) the legacy filters
can't see.

Each test here builds exactly that: a row the holder-keyed sweep provably
misses (the unpinned control beat), pins it to the changed source, and
asserts the widened sweep now reaches it — both the `set_dirty()` fan-out
and its `_affected_list_ids` mirror, which must stay in lockstep.
"""

from dataclasses import dataclass
from typing import Callable

import pytest

from gyrinx.content.models import (
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentUpgrade,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
    ContentWeaponAccessory,
)
from gyrinx.content.models.signal_handlers import _affected_list_ids
from gyrinx.core.models.list import (
    ListFighterEquipmentAssignment,
    ListFighterEquipmentAssignmentAccessory,
    ListFighterEquipmentAssignmentProfile,
    ListFighterEquipmentAssignmentUpgrade,
    PinState,
)
from gyrinx.core.tests.test_balance_sheet import fresh


@pytest.fixture
def sweep_ctx(
    user,
    make_list,
    make_list_fighter,
    make_content_fighter,
    content_house,
    make_equipment,
    make_weapon_profile,
):
    """A weapon held by a fighter the pin sources do NOT target.

    The pin sources built by each edge all key on ``origin_cf`` (the fighter
    context the gear was hypothetically acquired in) or on equipment the
    assignment doesn't hold — so the legacy sweep filters cannot reach this
    row, and only the pin clauses can.
    """
    lst = make_list("Sweep Gang")
    holder = make_list_fighter(lst, "Holder")
    origin_cf = make_content_fighter(
        type="Origin Digger", category="GANGER", house=content_house, base_cost=50
    )
    equipment = make_equipment("Lasgun", cost=15)
    other_equipment = make_equipment("Autogun", cost=20)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=holder, content_equipment=equipment
    )
    return {
        "lst": lst,
        "assignment": assignment,
        "origin_cf": origin_cf,
        "equipment": equipment,
        "other_equipment": other_equipment,
        "make_weapon_profile": make_weapon_profile,
    }


def _pin_base(ctx, **fk):
    ListFighterEquipmentAssignment.objects.filter(pk=ctx["assignment"].pk).update(
        pinned_base_amount=5, pinned_base_state=PinState.SOURCE, **fk
    )


def _attach_profile(ctx):
    profile = ctx["make_weapon_profile"](ctx["equipment"], name="Hotshot", cost=10)
    ctx["assignment"].weapon_profiles_field.add(profile)


def _build_cfeli(ctx):
    # Keyed to origin_cf: the holder-keyed legacy filter misses the row.
    return ContentFighterEquipmentListItem.objects.create(
        fighter=ctx["origin_cf"], equipment=ctx["equipment"], cost=5
    )


def _build_expansion_item(ctx):
    # Keyed to equipment the assignment doesn't hold — the situation the
    # equipment-keyed legacy filter can't see (e.g. the item's equipment FK
    # was re-pointed after acquisition). The pin must still reach the row.
    expansion = ContentEquipmentListExpansion.objects.create(name="Sweep Expansion")
    return ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion, equipment=ctx["other_equipment"], cost=5
    )


def _build_cfelwa(ctx):
    accessory = ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    ctx["assignment"].weapon_accessories_field.add(accessory)
    return ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=ctx["origin_cf"], weapon_accessory=accessory, cost=5
    )


def _build_cfelu(ctx):
    upgrade = ContentEquipmentUpgrade.objects.create(
        name="Mag", equipment=ctx["equipment"], cost=12
    )
    ctx["assignment"].upgrades_field.add(upgrade)
    return ContentFighterEquipmentListUpgrade.objects.create(
        fighter=ctx["origin_cf"], upgrade=upgrade, cost=5
    )


@dataclass(frozen=True)
class PinEdge:
    """One pin FK: which content source it targets, from which row model."""

    source: str  # content model whose cost change must sweep the pin
    row: str  # core model carrying the pin FK
    fk: str  # the pin FK field name on the row model
    build: Callable  # create the source (keyed so legacy filters miss)
    pin: Callable  # write the pin on the assignment/through row


PIN_EDGES = {
    "equipment-list-item->base": PinEdge(
        source="ContentFighterEquipmentListItem",
        row="ListFighterEquipmentAssignment",
        fk="pinned_equipment_list_item",
        build=_build_cfeli,
        pin=lambda ctx, source: _pin_base(ctx, pinned_equipment_list_item=source),
    ),
    "equipment-list-item->profile-row": PinEdge(
        source="ContentFighterEquipmentListItem",
        row="ListFighterEquipmentAssignmentProfile",
        fk="pinned_equipment_list_item",
        build=lambda ctx: (_attach_profile(ctx), _build_cfeli(ctx))[1],
        pin=lambda ctx, source: ctx["assignment"].profile_rows.update(
            pinned_equipment_list_item=source,
            pinned_amount=5,
            pin_state=PinState.SOURCE,
        ),
    ),
    "expansion-item->base": PinEdge(
        source="ContentEquipmentListExpansionItem",
        row="ListFighterEquipmentAssignment",
        fk="pinned_expansion_item",
        build=_build_expansion_item,
        pin=lambda ctx, source: _pin_base(ctx, pinned_expansion_item=source),
    ),
    "expansion-item->profile-row": PinEdge(
        source="ContentEquipmentListExpansionItem",
        row="ListFighterEquipmentAssignmentProfile",
        fk="pinned_expansion_item",
        build=lambda ctx: (_attach_profile(ctx), _build_expansion_item(ctx))[1],
        pin=lambda ctx, source: ctx["assignment"].profile_rows.update(
            pinned_expansion_item=source,
            pinned_amount=5,
            pin_state=PinState.SOURCE,
        ),
    ),
    "equipment-list-accessory->accessory-row": PinEdge(
        source="ContentFighterEquipmentListWeaponAccessory",
        row="ListFighterEquipmentAssignmentAccessory",
        fk="pinned_equipment_list_accessory",
        build=_build_cfelwa,
        pin=lambda ctx, source: ctx["assignment"].accessory_rows.update(
            pinned_equipment_list_accessory=source,
            pinned_amount=5,
            pin_state=PinState.SOURCE,
        ),
    ),
    "equipment-list-upgrade->upgrade-row": PinEdge(
        source="ContentFighterEquipmentListUpgrade",
        row="ListFighterEquipmentAssignmentUpgrade",
        fk="pinned_equipment_list_upgrade",
        build=_build_cfelu,
        pin=lambda ctx, source: ctx["assignment"].upgrade_rows.update(
            pinned_equipment_list_upgrade=source,
            pinned_amount=5,
            pin_state=PinState.SOURCE,
        ),
    ),
}


def _clear_dirty(ctx):
    ListFighterEquipmentAssignment.objects.filter(pk=ctx["assignment"].pk).update(
        dirty=False
    )


@pytest.mark.django_db
@pytest.mark.parametrize("edge_id", PIN_EDGES.keys())
def test_price_change_sweep_reaches_moved_pinned_rows(edge_id, sweep_ctx):
    """A cost change on a pin source dirties rows pinned to it — even rows
    the legacy context-keyed filters can't see — and its `_affected_list_ids`
    mirror names their list. The unpinned control beat proves the legacy
    filters genuinely miss this row, so the pin clause is what finds it.
    """
    edge = PIN_EDGES[edge_id]
    ctx = sweep_ctx
    assignment, lst = ctx["assignment"], ctx["lst"]
    source = edge.build(ctx)

    # Control beat: unpinned, this row is invisible to the sweep.
    _clear_dirty(ctx)
    source.cost = 6
    source.save()
    assert fresh(assignment).dirty is False
    assert lst.id not in _affected_list_ids(source)

    # Pinned, the same cost change reaches it through the pin FK.
    edge.pin(ctx, source)
    _clear_dirty(ctx)
    source.cost = 7
    source.save()
    assert fresh(assignment).dirty is True
    assert lst.id in _affected_list_ids(source)


def test_every_pin_fk_has_a_sweep_edge():
    """Every pinned_* FK on the assignment/through models appears in
    PIN_EDGES above — so adding a new pin FK without widening the sweeps
    (and extending this matrix) fails here, not silently in production.
    """
    row_models = [
        ListFighterEquipmentAssignment,
        ListFighterEquipmentAssignmentProfile,
        ListFighterEquipmentAssignmentAccessory,
        ListFighterEquipmentAssignmentUpgrade,
    ]
    discovered = {
        (field.related_model.__name__, model.__name__, field.name)
        for model in row_models
        for field in model._meta.get_fields()
        if field.concrete and field.is_relation and field.name.startswith("pinned_")
    }
    declared = {(edge.source, edge.row, edge.fk) for edge in PIN_EDGES.values()}
    assert discovered == declared


# --- The cost_expression watch ----------------------------------------------


@pytest.mark.django_db
def test_accessory_cost_expression_change_sweeps(sweep_ctx):
    """Editing an accessory's cost_expression reprices every assignment
    carrying it, so it must dirty them exactly like a flat-cost edit —
    previously it was unwatched and nothing moved.
    """
    ctx = sweep_ctx
    assignment = ctx["assignment"]
    accessory = ContentWeaponAccessory.objects.create(
        name="Percent Scope", cost=0, cost_expression="ceil(cost_int * 0.5 / 5) * 5"
    )
    assignment.weapon_accessories_field.add(accessory)

    # Control beat: a save with nothing changed sweeps nothing.
    _clear_dirty(ctx)
    accessory.save()
    assert fresh(assignment).dirty is False

    accessory.cost_expression = "ceil(cost_int * 1.0 / 5) * 5"
    accessory.save()
    assert fresh(assignment).dirty is True
