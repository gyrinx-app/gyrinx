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
from django.contrib.contenttypes.models import ContentType

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentUpgrade,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
    ContentWeaponAccessory,
)
from gyrinx.content.models.signal_handlers import (
    _affected_list_ids,
    _create_content_cost_change_actions,
)
from gyrinx.core.cost.pin_sweep import rewrite_pinned_amounts_for_list
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighterEquipmentAssignment,
    ListFighterEquipmentAssignmentAccessory,
    ListFighterEquipmentAssignmentProfile,
    ListFighterEquipmentAssignmentUpgrade,
    PinState,
)
from gyrinx.core.tasks import propagate_content_cost_change
from gyrinx.core.tests.test_balance_sheet import (
    assert_reconciles,
    buy_equipment,
    fresh,
    hire_fighter,
)


def _build_sweep_ctx(
    lst,
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
    return _build_sweep_ctx(
        make_list("Sweep Gang"),
        make_list_fighter,
        make_content_fighter,
        content_house,
        make_equipment,
        make_weapon_profile,
    )


@pytest.fixture
def campaign_sweep_ctx(
    user,
    campaign,
    make_list,
    make_list_fighter,
    make_content_fighter,
    content_house,
    make_equipment,
    make_weapon_profile,
):
    """The moved-gear context on a campaign list with a credits stake, so
    the full task flow (audit action + campaign credits) can be asserted."""
    lst = make_list("Sweep Campaign Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Stake",
        credits_delta=1000,
        update_credits=True,
    )
    return _build_sweep_ctx(
        fresh(lst),
        make_list_fighter,
        make_content_fighter,
        content_house,
        make_equipment,
        make_weapon_profile,
    )


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


def _build_cfeli_with_profile(ctx):
    _attach_profile(ctx)
    return _build_cfeli(ctx)


def _build_expansion_item_with_profile(ctx):
    _attach_profile(ctx)
    return _build_expansion_item(ctx)


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

    def read_pin(self, ctx):
        """Read back (amount, state, fk id) for this edge's pinned row."""
        if self.row == "ListFighterEquipmentAssignment":
            a = ListFighterEquipmentAssignment.objects.get(pk=ctx["assignment"].pk)
            return (
                a.pinned_base_amount,
                a.pinned_base_state,
                getattr(a, f"{self.fk}_id"),
            )
        accessor = {
            "ListFighterEquipmentAssignmentProfile": "profile_rows",
            "ListFighterEquipmentAssignmentAccessory": "accessory_rows",
            "ListFighterEquipmentAssignmentUpgrade": "upgrade_rows",
        }[self.row]
        row = getattr(ctx["assignment"], accessor).get()
        return (row.pinned_amount, row.pin_state, getattr(row, f"{self.fk}_id"))


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
        build=_build_cfeli_with_profile,
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
        build=_build_expansion_item_with_profile,
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


# --- Amount rewriting: corrections propagate to pinned rows ------------------


@pytest.mark.django_db
@pytest.mark.parametrize("edge_id", PIN_EDGES.keys())
def test_correction_rewrites_pinned_amount_and_books_it(edge_id, campaign_sweep_ctx):
    """Full flow per pin edge: the source is corrected, the task rewrites the
    pinned amount, recomputes, and books the per-row delta as an audit action
    with campaign credits. The caches-match-recompute assertion also pins the
    rewrite-BEFORE-recompute ordering: rewritten after, the caches would hold
    the old sum and disagree with the recompute below.
    """
    edge = PIN_EDGES[edge_id]
    ctx = campaign_sweep_ctx
    lst = ctx["lst"]
    source = edge.build(ctx)
    edge.pin(ctx, source)

    credits_before = fresh(lst).credits_current
    source.cost = 7  # pinned at 5
    source.save()
    _create_content_cost_change_actions(source)

    amount, state, fk_id = edge.read_pin(ctx)
    assert amount == 7
    assert fk_id == source.pk

    action = ListAction.objects.get(
        list=lst,
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=source.pk,
    )
    assert action.rating_delta == 2
    assert action.stash_delta == 0
    assert action.credits_delta == -2

    rf = fresh(lst)
    assert rf.credits_current == credits_before - 2
    facts = rf.facts_from_db(update=False)
    assert (facts.rating, facts.stash) == (rf.rating_current, rf.stash_current)


@pytest.mark.django_db
def test_purchase_in_enqueue_window_is_not_double_counted(
    user, campaign, make_list, make_content_fighter, content_house, make_equipment
):
    """A user purchase landing between enqueue and the task must keep its own
    audit trail: per-row amount deltas book exactly the correction, where the
    old snapshot-vs-recompute delta absorbed the purchase and double-charged
    campaign credits.
    """
    lst = make_list("Race Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Stake",
        credits_delta=1000,
        update_credits=True,
    )
    cf = make_content_fighter(
        type="Racer", category="GANGER", house=content_house, base_cost=50
    )
    fighter = hire_fighter(user, fresh(lst), cf, name="Bob")
    equipment = make_equipment("Lasgun", cost=15)
    item = ContentFighterEquipmentListItem.objects.create(
        fighter=cf, equipment=equipment, cost=5
    )
    assignment = buy_equipment(user, fresh(lst), fighter, equipment)
    # Pin at the booked acquisition price (what Phase 7 will write).
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=5,
        pinned_base_state=PinState.SOURCE,
        pinned_equipment_list_item=item,
    )
    assert_reconciles(lst)

    # The correction is enqueued with a pre-change snapshot...
    before = {str(lst.id): [fresh(lst).rating_current, fresh(lst).stash_current]}
    item.cost = 8
    item.save()

    # ...and a purchase lands inside the window, before the task runs.
    other = make_equipment("Autogun", cost=30)
    buy_equipment(user, fresh(lst), fresh(fighter), other)
    credits_after_purchase = fresh(lst).credits_current

    ct = ContentType.objects.get_for_model(type(item))
    propagate_content_cost_change.func(ct.id, str(item.pk), before)

    # Exactly the +3 correction moves; the +30 purchase is not re-booked.
    assert fresh(lst).credits_current == credits_after_purchase - 3
    action = ListAction.objects.get(
        list=lst,
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=item.pk,
    )
    assert action.rating_delta == 3
    assert action.credits_delta == -3
    assert_reconciles(lst)


# --- Sweep-domain partition by pin_state --------------------------------------


@pytest.mark.django_db
def test_orphaned_and_source_rows_ignore_catalog_sweeps(sweep_ctx):
    """Catalog amount-copy sweeps only touch CATALOG rows: ORPHANED amounts
    are frozen by definition, and SOURCE amounts belong to their override
    source, not the catalog price."""
    ctx = sweep_ctx
    assignment, equipment = ctx["assignment"], ctx["equipment"]

    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=5, pinned_base_state=PinState.ORPHANED
    )
    equipment.cost = "25"
    equipment.save()
    _create_content_cost_change_actions(equipment)
    a = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
    assert (a.pinned_base_amount, a.pinned_base_state) == (5, PinState.ORPHANED)

    source = _build_cfelwa(ctx)
    assignment.accessory_rows.update(
        pinned_equipment_list_accessory=source,
        pinned_amount=5,
        pin_state=PinState.SOURCE,
    )
    accessory = source.weapon_accessory
    accessory.cost = 20
    accessory.save()
    _create_content_cost_change_actions(accessory)
    row = assignment.accessory_rows.get()
    assert (row.pinned_amount, row.pin_state) == (5, PinState.SOURCE)


# --- Derived amounts re-derive, never copy ------------------------------------


@pytest.mark.django_db
def test_single_stack_lower_rung_correction_rederives_higher_rung(sweep_ctx):
    """SINGLE stacks price cumulatively: correcting rung 0 reprices a DERIVED
    pinned row holding rung 1, and the widened upgrade sweep reaches that
    holder even though it doesn't hold rung 0 itself."""
    ctx = sweep_ctx
    assignment, equipment = ctx["assignment"], ctx["equipment"]
    rung0 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Rung 0", position=0, cost=10
    )
    rung1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Rung 1", position=1, cost=20
    )
    assignment.upgrades_field.add(rung1)
    assignment.upgrade_rows.update(pinned_amount=30, pin_state=PinState.DERIVED)

    _clear_dirty(ctx)
    rung0.cost = 20
    rung0.save()
    # The rung-1 holder is dirtied by the rung-0 correction...
    assert fresh(assignment).dirty is True
    assert ctx["lst"].id in _affected_list_ids(rung0)

    # ...and its cumulative receipt moves by the rung's delta: 30 + 10.
    _create_content_cost_change_actions(rung0, old_cost=10)
    row = assignment.upgrade_rows.get()
    assert (row.pinned_amount, row.pin_state) == (40, PinState.DERIVED)


@pytest.mark.django_db
def test_base_correction_cascades_to_expression_accessory(sweep_ctx):
    """Rewriting a pinned base cascades to same-assignment DERIVED expression
    accessories, which re-derive from the new base. The list here is outside
    the action system (no latest_action) — amounts must be rewritten anyway,
    or a later lazy recompute would read stale prices forever."""
    ctx = sweep_ctx
    assignment, equipment = ctx["assignment"], ctx["equipment"]
    accessory = ContentWeaponAccessory.objects.create(
        name="Percent Scope", cost=0, cost_expression="ceil(cost_int * 0.5 / 5) * 5"
    )
    assignment.weapon_accessories_field.add(accessory)
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=15, pinned_base_state=PinState.CATALOG
    )
    assignment.accessory_rows.update(
        pinned_amount=10,  # ceil(15 * 0.5 / 5) * 5
        pin_state=PinState.DERIVED,
    )

    equipment.cost = "25"
    equipment.save()
    _create_content_cost_change_actions(equipment)

    a = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
    assert a.pinned_base_amount == 25
    assert assignment.accessory_rows.get().pinned_amount == 15  # ceil(25*0.5/5)*5


# --- Delete-side: sources disappear, amounts stand -----------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("edge_id", PIN_EDGES.keys())
def test_deleting_price_source_orphans_pins(
    edge_id, campaign_sweep_ctx, django_capture_on_commit_callbacks
):
    """Deleting a price source freezes the rows pinned to it: the amount is
    kept, the FK cleared, the state flips to ORPHANED, an audit action records
    the attribution loss, and no caches move (nothing changed price)."""
    edge = PIN_EDGES[edge_id]
    ctx = campaign_sweep_ctx
    lst = ctx["lst"]
    source = edge.build(ctx)
    edge.pin(ctx, source)
    rf = fresh(lst)
    caches_before = (rf.rating_current, rf.stash_current, rf.credits_current)
    source_pk = source.pk

    # The audit is written after commit (the delete collector must not see
    # new ListAction rows for lists dying in the same cascade).
    with django_capture_on_commit_callbacks(execute=True):
        source.delete()

    assert edge.read_pin(ctx) == (5, PinState.ORPHANED, None)
    action = ListAction.objects.get(
        list=lst,
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=source_pk,
    )
    assert "price source deleted" in action.description
    assert (action.rating_delta, action.stash_delta, action.credits_delta) == (0, 0, 0)
    rf = fresh(lst)
    assert (rf.rating_current, rf.stash_current, rf.credits_current) == caches_before


# --- Resolution masks: rewritten amounts that must book NO movement ----------


def _assert_no_correction_booked(lst, source, credits_before):
    assert not ListAction.objects.filter(
        list=lst,
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=source.pk,
    ).exists()
    assert fresh(lst).credits_current == credits_before


@pytest.mark.django_db
def test_total_cost_override_masks_correction_delta(campaign_sweep_ctx):
    """A fixed assignment total outranks the pin: the amount is rewritten
    (provenance stays current) but the resolved value never moved, so no
    action is booked and no credits are charged."""
    ctx = campaign_sweep_ctx
    lst = ctx["lst"]
    edge = PIN_EDGES["equipment-list-item->base"]
    source = edge.build(ctx)
    edge.pin(ctx, source)
    ListFighterEquipmentAssignment.objects.filter(pk=ctx["assignment"].pk).update(
        total_cost_override=10
    )

    credits_before = fresh(lst).credits_current
    source.cost = 7
    source.save()
    _create_content_cost_change_actions(source)

    assert edge.read_pin(ctx)[0] == 7  # rewritten
    _assert_no_correction_booked(lst, source, credits_before)


@pytest.mark.django_db
def test_cost_override_masks_base_correction_delta(campaign_sweep_ctx):
    """A user base override outranks the base pin the same way."""
    ctx = campaign_sweep_ctx
    lst = ctx["lst"]
    edge = PIN_EDGES["equipment-list-item->base"]
    source = edge.build(ctx)
    edge.pin(ctx, source)
    ListFighterEquipmentAssignment.objects.filter(pk=ctx["assignment"].pk).update(
        cost_override=3
    )

    credits_before = fresh(lst).credits_current
    source.cost = 7
    source.save()
    _create_content_cost_change_actions(source)

    assert edge.read_pin(ctx)[0] == 7
    _assert_no_correction_booked(lst, source, credits_before)


@pytest.mark.django_db
def test_from_default_component_mask_forces_snapshot_fallback(sweep_ctx):
    """From-default assignments free SOME components by membership — the
    per-row maths can't price that, so the sweep flags the snapshot fallback
    (while still rewriting the amount)."""
    ctx = sweep_ctx
    assignment, equipment = ctx["assignment"], ctx["equipment"]
    profile = ctx["make_weapon_profile"](equipment, name="Hotshot", cost=5)
    assignment.weapon_profiles_field.add(profile)
    assignment.profile_rows.update(pinned_amount=5, pin_state=PinState.CATALOG)
    default = ContentFighterDefaultAssignment.objects.create(
        fighter=assignment.list_fighter.content_fighter, equipment=equipment
    )
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        from_default_assignment=default
    )

    profile.cost = 7
    sweep = rewrite_pinned_amounts_for_list(profile, ctx["lst"])
    assert sweep.has_masked is True
    assert sweep.use_row_deltas is False
    assert assignment.profile_rows.get().pinned_amount == 7  # still rewritten


@pytest.mark.django_db
def test_unpinned_expression_rider_forces_snapshot_fallback(sweep_ctx):
    """An UNPINNED expression accessory reprices live off a rewritten base:
    its movement is invisible to per-row deltas, so it must flip the list to
    the snapshot fallback."""
    ctx = sweep_ctx
    assignment, equipment = ctx["assignment"], ctx["equipment"]
    accessory = ContentWeaponAccessory.objects.create(
        name="Percent Scope", cost=0, cost_expression="ceil(cost_int * 0.5 / 5) * 5"
    )
    assignment.weapon_accessories_field.add(accessory)
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=15, pinned_base_state=PinState.CATALOG
    )

    equipment.cost = "25"
    sweep = rewrite_pinned_amounts_for_list(equipment, ctx["lst"])
    assert sweep.has_unpinned is True
    assert sweep.use_row_deltas is False
    a = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
    assert a.pinned_base_amount == 25  # base still rewritten


# --- Archived rows: amounts maintained, caches untouched ----------------------


@pytest.mark.django_db
def test_archived_rows_rewritten_without_cache_movement(campaign_sweep_ctx):
    """A list reachable only through an archived pinned row still gets the
    amount rewrite (an unarchive must not resurrect a stale price), but no
    dirty-marking, no action, and no cache movement."""
    ctx = campaign_sweep_ctx
    lst = ctx["lst"]
    edge = PIN_EDGES["equipment-list-item->base"]
    source = edge.build(ctx)
    edge.pin(ctx, source)
    ListFighterEquipmentAssignment.objects.filter(pk=ctx["assignment"].pk).update(
        archived=True, dirty=False
    )

    credits_before = fresh(lst).credits_current
    source.cost = 7
    source.save()
    _create_content_cost_change_actions(source)

    assert edge.read_pin(ctx)[0] == 7
    assert fresh(ctx["assignment"]).dirty is False
    _assert_no_correction_booked(lst, source, credits_before)


# --- Catalog sweeps: the components' own price corrections -------------------


def _catalog_profile(ctx):
    profile = ctx["make_weapon_profile"](ctx["equipment"], name="Hotshot", cost=5)
    ctx["assignment"].weapon_profiles_field.add(profile)
    ctx["assignment"].profile_rows.update(pinned_amount=5, pin_state=PinState.CATALOG)
    return profile, lambda: ctx["assignment"].profile_rows.get().pinned_amount


def _catalog_accessory(ctx):
    accessory = ContentWeaponAccessory.objects.create(name="Flat Scope", cost=5)
    ctx["assignment"].weapon_accessories_field.add(accessory)
    ctx["assignment"].accessory_rows.update(pinned_amount=5, pin_state=PinState.CATALOG)
    return accessory, lambda: ctx["assignment"].accessory_rows.get().pinned_amount


def _catalog_multi_upgrade(ctx):
    multi_equipment = ContentEquipment.objects.create(
        name="Multi Gun", cost=10, upgrade_mode=ContentEquipment.UpgradeMode.MULTI
    )
    multi_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=ctx["assignment"].list_fighter, content_equipment=multi_equipment
    )
    upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=multi_equipment, name="Mag", cost=5
    )
    multi_assignment.upgrades_field.add(upgrade)
    multi_assignment.upgrade_rows.update(pinned_amount=5, pin_state=PinState.CATALOG)
    return upgrade, lambda: multi_assignment.upgrade_rows.get().pinned_amount


CATALOG_KINDS = {
    "weapon-profile": _catalog_profile,
    "weapon-accessory": _catalog_accessory,
    "multi-upgrade": _catalog_multi_upgrade,
}


@pytest.mark.django_db
@pytest.mark.parametrize("kind", CATALOG_KINDS.keys())
def test_catalog_correction_rewrites_component_amount_and_books_it(
    kind, campaign_sweep_ctx
):
    """CATALOG-attributed component rows copy their own content price when
    it is corrected, and the correction books per-row."""
    ctx = campaign_sweep_ctx
    lst = ctx["lst"]
    source, read_amount = CATALOG_KINDS[kind](ctx)

    credits_before = fresh(lst).credits_current
    source.cost = 7
    source.save()
    _create_content_cost_change_actions(source)

    assert read_amount() == 7
    action = ListAction.objects.get(
        list=lst,
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=source.pk,
    )
    assert (action.rating_delta, action.stash_delta, action.credits_delta) == (
        2,
        0,
        -2,
    )
    assert fresh(lst).credits_current == credits_before - 2


@pytest.mark.django_db
def test_expression_edit_rederives_derived_amount_and_books(campaign_sweep_ctx):
    """Editing an accessory's cost_expression re-derives DERIVED rows through
    the full task flow and books the movement."""
    ctx = campaign_sweep_ctx
    lst = ctx["lst"]
    accessory = ContentWeaponAccessory.objects.create(
        name="Percent Scope", cost=0, cost_expression="ceil(cost_int * 0.5 / 5) * 5"
    )
    ctx["assignment"].weapon_accessories_field.add(accessory)
    ctx["assignment"].accessory_rows.update(
        pinned_amount=10,  # ceil(15 * 0.5 / 5) * 5 against the live 15 base
        pin_state=PinState.DERIVED,
    )

    credits_before = fresh(lst).credits_current
    accessory.cost_expression = "ceil(cost_int * 1.0 / 5) * 5"
    accessory.save()
    _create_content_cost_change_actions(accessory)

    assert ctx["assignment"].accessory_rows.get().pinned_amount == 15
    action = ListAction.objects.get(
        list=lst,
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=accessory.pk,
    )
    assert (action.rating_delta, action.credits_delta) == (5, -5)
    assert fresh(lst).credits_current == credits_before - 5


@pytest.mark.django_db
def test_stash_side_correction_books_stash_delta(campaign_sweep_ctx):
    """A pinned row held by the stash books its correction as stash movement,
    not rating movement."""
    ctx = campaign_sweep_ctx
    lst = ctx["lst"]
    stash = lst.ensure_stash()
    stash_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash, content_equipment=ctx["equipment"]
    )
    item = _build_cfeli(ctx)
    ListFighterEquipmentAssignment.objects.filter(pk=stash_assignment.pk).update(
        pinned_base_amount=5,
        pinned_base_state=PinState.SOURCE,
        pinned_equipment_list_item=item,
    )

    credits_before = fresh(lst).credits_current
    item.cost = 7
    item.save()
    _create_content_cost_change_actions(item)

    action = ListAction.objects.get(
        list=lst,
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=item.pk,
    )
    assert (action.rating_delta, action.stash_delta, action.credits_delta) == (
        0,
        2,
        -2,
    )
    assert fresh(lst).credits_current == credits_before - 2


@pytest.mark.django_db
def test_expansion_item_blank_cost_rewrites_to_base_price(sweep_ctx):
    """An expansion item's blank cost means "use the base price" — clearing
    the override must rewrite pinned amounts to the underlying equipment (or
    profile) price, not to zero."""
    ctx = sweep_ctx
    base_edge = PIN_EDGES["expansion-item->base"]
    source = base_edge.build(ctx)
    base_edge.pin(ctx, source)

    source.cost = None
    source.save()
    _create_content_cost_change_actions(source)

    # The item prices other_equipment (cost 20): blank falls back to that.
    assert base_edge.read_pin(ctx)[0] == 20

    # Same fallback for a profile-priced expansion pin: blank -> profile cost.
    profile_edge = PIN_EDGES["expansion-item->profile-row"]
    profile_source = ContentEquipmentListExpansionItem.objects.create(
        expansion=source.expansion,
        equipment=ctx["equipment"],
        weapon_profile=ctx["make_weapon_profile"](
            ctx["equipment"], name="Blank Shot", cost=12
        ),
        cost=5,
    )
    ctx["assignment"].weapon_profiles_field.add(profile_source.weapon_profile)
    ctx["assignment"].profile_rows.update(
        pinned_expansion_item=profile_source, pinned_amount=5, pin_state=PinState.SOURCE
    )

    profile_source.cost = None
    profile_source.save()
    _create_content_cost_change_actions(profile_source)

    assert profile_edge.read_pin(ctx)[0] == 12


# --- Deep-review follow-ups ----------------------------------------------------


@pytest.mark.django_db
def test_house_cascade_delete_survives_pin_orphaning(
    campaign_sweep_ctx, content_house, django_capture_on_commit_callbacks
):
    """Deleting a ContentHouse cascades through its fighters' price rows AND
    its lists. The orphan audit must not insert ledger rows for gangs dying
    in the same cascade — previously an IntegrityError at commit rolled the
    whole deletion back."""
    ctx = campaign_sweep_ctx
    edge = PIN_EDGES["equipment-list-item->base"]
    source = edge.build(ctx)
    edge.pin(ctx, source)
    lst_id = ctx["lst"].id

    with django_capture_on_commit_callbacks(execute=True):
        content_house.delete()

    assert not List.objects.filter(id=lst_id).exists()
    assert not ListAction.objects.filter(list_id=lst_id).exists()


@pytest.mark.django_db
def test_cfelu_lower_rung_override_correction_reaches_higher_rung(sweep_ctx):
    """A fighter-specific upgrade override applies PER RUNG inside SINGLE
    cumulative pricing, so correcting it reprices holders of higher rungs —
    previously missed by the same-rung-only filter (live bug, pins or not).
    """
    ctx = sweep_ctx
    assignment, equipment = ctx["assignment"], ctx["equipment"]
    rung0 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Rung 0", position=0, cost=10
    )
    rung1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Rung 1", position=1, cost=20
    )
    assignment.upgrades_field.add(rung1)  # holds only the HIGHER rung
    override = ContentFighterEquipmentListUpgrade.objects.create(
        fighter=assignment.list_fighter.content_fighter, upgrade=rung0, cost=5
    )

    _clear_dirty(ctx)
    override.cost = 8
    override.save()
    assert fresh(assignment).dirty is True
    assert ctx["lst"].id in _affected_list_ids(override)


@pytest.mark.django_db
def test_derived_expression_on_unpinned_base_rederives(sweep_ctx):
    """A DERIVED formula accessory on an UNPINNED base must re-derive when
    the base's catalog price changes: the base reprices live, and resolution
    would read the stale derived amount forever."""
    ctx = sweep_ctx
    assignment, equipment = ctx["assignment"], ctx["equipment"]
    accessory = ContentWeaponAccessory.objects.create(
        name="Percent Scope", cost=0, cost_expression="ceil(cost_int * 0.5 / 5) * 5"
    )
    assignment.weapon_accessories_field.add(accessory)
    assignment.accessory_rows.update(
        pinned_amount=10,  # derived from the live 15 base
        pin_state=PinState.DERIVED,
    )

    # Saved, not just set in memory: re-derivation resolves the live base
    # from the database, exactly as the post-commit task does.
    equipment.cost = "25"
    equipment.save()
    sweep = rewrite_pinned_amounts_for_list(equipment, ctx["lst"])

    assert assignment.accessory_rows.get().pinned_amount == 15
    assert sweep.has_unpinned is True  # unpinned base repriced live


@pytest.mark.django_db
def test_archived_from_default_row_does_not_mask(sweep_ctx):
    """An archived default-kit row is rewritten but must not stickily force
    the whole list onto the snapshot fallback — archived rows move nothing
    and mask nothing."""
    ctx = sweep_ctx
    assignment, equipment = ctx["assignment"], ctx["equipment"]
    profile = ctx["make_weapon_profile"](equipment, name="Hotshot", cost=5)
    assignment.weapon_profiles_field.add(profile)
    assignment.profile_rows.update(pinned_amount=5, pin_state=PinState.CATALOG)
    default = ContentFighterDefaultAssignment.objects.create(
        fighter=assignment.list_fighter.content_fighter, equipment=equipment
    )
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        from_default_assignment=default, archived=True
    )

    profile.cost = 7
    sweep = rewrite_pinned_amounts_for_list(profile, ctx["lst"])

    assert sweep.has_masked is False
    assert sweep.use_row_deltas is True
    assert assignment.profile_rows.get().pinned_amount == 7  # still rewritten


@pytest.mark.django_db
def test_expansion_item_zero_to_blank_sweeps(sweep_ctx):
    """cost=0 means "free" and blank means "use the base price" — the
    transition reprices, but both coerce to 0 in the int helpers, so it was
    previously invisible to change detection."""
    ctx = sweep_ctx
    edge = PIN_EDGES["expansion-item->base"]
    source = edge.build(ctx)
    ContentEquipmentListExpansionItem.objects.filter(pk=source.pk).update(cost=0)
    source.refresh_from_db()
    edge.pin(ctx, source)
    ListFighterEquipmentAssignment.objects.filter(pk=ctx["assignment"].pk).update(
        pinned_base_amount=0
    )

    _clear_dirty(ctx)
    source.cost = None
    source.save()
    assert fresh(ctx["assignment"]).dirty is True  # the raw-value watch fired

    _create_content_cost_change_actions(source)
    assert edge.read_pin(ctx)[0] == 20  # blank -> other_equipment's base price


@pytest.mark.django_db
def test_cancelling_rating_and_stash_deltas_still_book(campaign_sweep_ctx):
    """+2 rating / -2 stash sums to zero but both books moved — the action
    must still be recorded or the ledger chain breaks silently."""
    ctx = campaign_sweep_ctx
    lst = ctx["lst"]
    item = _build_cfeli(ctx)  # cost 5

    # Rating-side row pinned below the corrected price (+2)...
    ListFighterEquipmentAssignment.objects.filter(pk=ctx["assignment"].pk).update(
        pinned_base_amount=5,
        pinned_base_state=PinState.SOURCE,
        pinned_equipment_list_item=item,
    )
    # ...stash-side row pinned above it (-2).
    stash = lst.ensure_stash()
    stash_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash, content_equipment=ctx["equipment"]
    )
    ListFighterEquipmentAssignment.objects.filter(pk=stash_assignment.pk).update(
        pinned_base_amount=9,
        pinned_base_state=PinState.SOURCE,
        pinned_equipment_list_item=item,
    )

    item.cost = 7
    item.save()
    _create_content_cost_change_actions(item)

    action = ListAction.objects.get(
        list=lst,
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=item.pk,
    )
    assert (action.rating_delta, action.stash_delta, action.credits_delta) == (
        2,
        -2,
        0,
    )


# --- SINGLE-stack receipts: corrections apply BY DELTA --------------------------


@pytest.fixture
def single_stack_ctx(campaign_sweep_ctx):
    """A REAL cumulative-stack receipt: rung 0 discounted by a per-rung
    override (10 -> 6 for the holder's fighter type), the holder owns rung 1
    (catalog 20), so acquisition pins the override-inclusive walk: 26."""
    from gyrinx.core.cost.pinning import pin_assignment

    ctx = campaign_sweep_ctx
    holder_cf = ctx["assignment"].list_fighter.content_fighter
    rung0 = ContentEquipmentUpgrade.objects.create(
        equipment=ctx["equipment"], name="Rung 0", position=0, cost=10
    )
    override = ContentFighterEquipmentListUpgrade.objects.create(
        fighter=holder_cf, upgrade=rung0, cost=6
    )
    rung1 = ContentEquipmentUpgrade.objects.create(
        equipment=ctx["equipment"], name="Rung 1", position=1, cost=20
    )
    ctx["assignment"].upgrades_field.add(rung1)
    pin_assignment(ctx["assignment"])
    row = ctx["assignment"].upgrade_rows.get()
    assert (row.pinned_amount, row.pin_state) == (26, PinState.DERIVED)
    ctx.update(rung0=rung0, rung1=rung1, override=override)
    return ctx


@pytest.mark.django_db
def test_single_stack_catalog_correction_moves_receipt_by_delta(single_stack_ctx):
    """Correcting rung 1's catalog price (+5) moves the receipt by exactly
    +5 — it must NOT re-derive to the raw catalog sum, which would destroy
    the acquisition discount on rung 0 and overbook the change."""
    ctx = single_stack_ctx
    ctx["rung1"].cost = 25
    ctx["rung1"].save()
    _create_content_cost_change_actions(ctx["rung1"], old_cost=20)

    row = ctx["assignment"].upgrade_rows.get()
    assert row.pinned_amount == 31  # 26 + 5, NOT 35 (10 + 25)
    action = ListAction.objects.get(
        list=ctx["lst"],
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=ctx["rung1"].pk,
    )
    assert (action.rating_delta, action.credits_delta) == (5, -5)


@pytest.mark.django_db
def test_single_stack_masked_rung_correction_leaves_receipt(single_stack_ctx):
    """Correcting the CATALOG price of a rung the holder's override masks
    changes nothing they pay: the receipt stands and nothing is booked."""
    ctx = single_stack_ctx
    ctx["rung0"].cost = 12
    ctx["rung0"].save()
    _create_content_cost_change_actions(ctx["rung0"], old_cost=10)

    assert ctx["assignment"].upgrade_rows.get().pinned_amount == 26
    assert not ListAction.objects.filter(
        list=ctx["lst"],
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=ctx["rung0"].pk,
    ).exists()


@pytest.mark.django_db
def test_single_stack_override_correction_reaches_receipt_by_delta(single_stack_ctx):
    """Correcting the per-rung override (6 -> 8) reaches the DERIVED receipt
    it priced — previously invisible to sweeps (no FK on amount-snapshots)."""
    ctx = single_stack_ctx
    ctx["override"].cost = 8
    ctx["override"].save()
    _create_content_cost_change_actions(ctx["override"], old_cost=6)

    assert ctx["assignment"].upgrade_rows.get().pinned_amount == 28  # 26 + 2
    action = ListAction.objects.get(
        list=ctx["lst"],
        action_type=ListActionType.CONTENT_COST_CHANGE,
        subject_id=ctx["override"].pk,
    )
    assert (action.rating_delta, action.credits_delta) == (2, -2)


@pytest.mark.django_db
def test_single_stack_without_old_cost_masks_instead_of_guessing(single_stack_ctx):
    """A direct sweep call with no pre-change value cannot compute the
    delta: the receipt stands and the list flags the snapshot fallback."""
    ctx = single_stack_ctx
    ctx["rung1"].cost = 25
    ctx["rung1"].save()
    sweep = rewrite_pinned_amounts_for_list(ctx["rung1"], ctx["lst"])

    assert sweep.has_masked is True
    assert sweep.use_row_deltas is False
    assert ctx["assignment"].upgrade_rows.get().pinned_amount == 26
