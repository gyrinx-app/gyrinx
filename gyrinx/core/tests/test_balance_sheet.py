"""Balance-sheet harness: calibration meta-tests and the situation matrix.

Part of the cost-pinning programme (#1826). The meta-tests prove the
instrument itself: every seeded cache corruption must be caught and localised
to the tampered level, with zero false alarms on healthy data built through
the real handler flows. The situation matrix then exercises app flows
cell-by-cell; known drift producers are pinned as strict xfails until the
phase that fixes them.

Every cell uses the same two-beat check: the sheet must reconcile immediately
after the action, and again after a forced full recompute — the second beat
is what catches "cache says X, recompute says Y" divergence.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipmentUpgrade,
    ContentFighterEquipmentListItem,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.core.cost.balance_sheet import (
    _rows_source_repr,
    _source_repr,
    build_balance_sheet,
)
from gyrinx.core.handlers.equipment.cost_override import (
    handle_equipment_cost_override,
)
from gyrinx.core.handlers.equipment.purchase import (
    handle_accessory_purchase,
    handle_equipment_purchase,
    handle_equipment_upgrade,
    handle_weapon_profile_purchase,
)
from gyrinx.core.handlers.equipment.reassignment import (
    handle_equipment_reassignment,
)
from gyrinx.core.handlers.equipment.removal import (
    handle_equipment_component_removal,
    handle_equipment_removal,
)
from gyrinx.core.handlers.fighter.hire_clone import handle_fighter_hire
from gyrinx.core.handlers.fighter.kill import handle_fighter_kill
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    PinState,
)
from gyrinx.core.models.pack import CustomContentPackItem
from gyrinx.core.tasks import propagate_content_cost_change

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hire_fighter(user, lst, content_fighter, name="Fighter"):
    """Add a fighter through the real hire flow (propagation + ListAction)."""
    lst = List.objects.get(pk=lst.pk)
    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name=name,
    )
    return handle_fighter_hire(user=user, lst=lst, fighter=fighter).fighter


def fresh(obj):
    """Refetch a model instance, mimicking a request boundary.

    Handlers propagate deltas onto the instances they are given
    (`propagate_from_fighter` writes `rating_current + delta` back as an
    absolute value), so they must be handed freshly-fetched objects the way a
    view would. Chaining handlers against stale in-memory instances writes
    stale absolute values — a harness artifact, not an app flow.
    """
    if isinstance(obj, ListFighterEquipmentAssignment):
        # Views hand handlers assignments fetched via with_related_data(),
        # whose component prefetches all route through all_content() so
        # pack-scoped profiles, accessories, and upgrades survive the fetch
        # (#1933). A plain fetch would drop them and misprice pack gear.
        return ListFighterEquipmentAssignment.objects.with_related_data().get(pk=obj.pk)
    return type(obj).objects.get(pk=obj.pk)


def buy_equipment(user, lst, fighter, equipment):
    """Buy equipment through the real purchase flow."""
    fighter = fresh(fighter)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    handle_equipment_purchase(
        user=user, lst=fresh(lst), fighter=fighter, assignment=assignment
    )
    return assignment


def force_recompute(lst):
    """Mark every cache dirty and recompute leaf-up from live cost_int()."""
    ListFighterEquipmentAssignment.objects.filter(list_fighter__list=lst).update(
        dirty=True
    )
    ListFighter.objects.filter(list=lst).update(dirty=True)
    List.objects.filter(pk=lst.pk).update(dirty=True)
    lst.refresh_from_db()
    lst.facts_from_db(update=True)


def fresh_sheet(lst):
    lst.refresh_from_db()
    return build_balance_sheet(lst)


def assert_reconciles(lst):
    """The two-beat check: reconcile now, and again after forced recompute."""
    problems = fresh_sheet(lst).reconcile()
    assert problems == [], f"immediately after action: {problems}"

    force_recompute(lst)

    problems = fresh_sheet(lst).reconcile()
    assert problems == [], f"after forced recompute: {problems}"


def assert_problems(problems, must_mention, must_not_mention=()):
    """Every `must_mention` marker appears; no `must_not_mention` marker does."""
    joined = "\n".join(problems)
    for marker in must_mention:
        assert marker in joined, (
            f"expected a problem mentioning {marker!r}, got: {problems}"
        )
    for marker in must_not_mention:
        assert marker not in joined, (
            f"expected NO problem mentioning {marker!r}, got: {problems}"
        )


class ContentSource:
    """The catalog-vs-pack axis for matrix content.

    Every cell that uses the `gear` factory runs twice: once with plain
    catalog content, once with the identical content scoped to a subscribed
    CustomContentPack. Pack content is invisible to the default
    ContentManager and only surfaced by all_content()/with_packs(), so any
    cost path that fetches content carelessly prices pack gear differently —
    a class of drift the catalog variant can never see.
    """

    def __init__(self, pack=None):
        self.pack = pack

    @property
    def name(self):
        return "pack" if self.pack else "catalog"

    def subscribe(self, lst):
        if self.pack:
            lst.packs.add(self.pack)

    def register(self, obj):
        if self.pack:
            CustomContentPackItem.objects.create(
                pack=self.pack,
                content_type=ContentType.objects.get_for_model(type(obj)),
                object_id=obj.pk,
                owner=self.pack.owner,
            )
        return obj


@pytest.fixture(params=["catalog", "pack"])
def content_source(request, make_pack):
    if request.param == "pack":
        return ContentSource(make_pack("Axis Pack"))
    return ContentSource()


@pytest.fixture
def gear(content_source, make_equipment, make_weapon_profile):
    """Content factory building gear on the current side of the axis."""

    class Gear:
        def equipment(self, name="Lasgun", cost=15, **kwargs):
            return content_source.register(make_equipment(name, cost=cost, **kwargs))

        def accessory(self, name="Scope", cost=8, **kwargs):
            return content_source.register(
                ContentWeaponAccessory.objects.create(name=name, cost=cost, **kwargs)
            )

        def profile(self, equipment, name="Hotshot", cost=10, **kwargs):
            return content_source.register(
                make_weapon_profile(equipment, name=name, cost=cost, **kwargs)
            )

        def upgrade(self, equipment, name="Extended mag", cost=12, **kwargs):
            return content_source.register(
                ContentEquipmentUpgrade.objects.create(
                    name=name, equipment=equipment, cost=cost, **kwargs
                )
            )

    return Gear()


@pytest.fixture
def healthy_list(user, make_list, content_fighter, content_source, gear):
    """A list built entirely through real flows: one fighter, one weapon.

    Parametrized over the catalog-vs-pack axis: everything downstream of
    this fixture (meta-tests included) runs on both sides.
    """
    lst = make_list("Balance Gang")
    content_source.subscribe(lst)
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    equipment = gear.equipment("Lasgun", cost=15)
    assignment = buy_equipment(user, lst, fighter, equipment)
    lst.refresh_from_db()
    return lst, fighter, assignment


# ---------------------------------------------------------------------------
# Meta-tests: calibrate the instrument before trusting it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_meta_empty_list_reconciles(make_list):
    lst = make_list("Empty Gang")
    assert_reconciles(lst)


@pytest.mark.django_db
def test_meta_healthy_list_reconciles(healthy_list):
    lst, _, _ = healthy_list
    assert_reconciles(lst)


@pytest.mark.django_db
def test_meta_decomposition_matches_live_cost(healthy_list):
    """The sheet's decomposition must agree with the live cost computation.

    If cost semantics change and the sheet doesn't track them, this fails
    loudly instead of the sheet silently reconciling wrong numbers.
    """
    lst, fighter, assignment = healthy_list
    sheet = fresh_sheet(lst)

    fighter.refresh_from_db()
    assignment.refresh_from_db()

    fb = sheet.fighters[0]
    assert fb.computed == fighter.cost_int()
    ab = fb.assignments[0]
    assert ab.computed == assignment.cost_int()
    assert sheet.computed_rating == sum(
        f.cost_int() for f in lst.fighters() if not f.is_stash
    )


@pytest.mark.django_db
def test_meta_detects_assignment_cache_tamper(healthy_list):
    lst, _, assignment = healthy_list
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        rating_current=assignment.rating_current + 7
    )
    problems = fresh_sheet(lst).reconcile()
    assert_problems(
        problems,
        must_mention=["assignment 'Lasgun'"],
        must_not_mention=["fighter 'Bob':", "list rating", "credits"],
    )


@pytest.mark.django_db
def test_meta_detects_fighter_cache_tamper(healthy_list):
    lst, fighter, _ = healthy_list
    ListFighter.objects.filter(pk=fighter.pk).update(
        rating_current=fighter.rating_current + 7
    )
    problems = fresh_sheet(lst).reconcile()
    assert_problems(
        problems,
        must_mention=["fighter 'Bob':"],
        must_not_mention=["assignment 'Lasgun'", "list rating", "credits"],
    )


@pytest.mark.django_db
def test_meta_detects_list_rating_tamper(healthy_list):
    lst, _, _ = healthy_list
    List.objects.filter(pk=lst.pk).update(rating_current=lst.rating_current + 7)
    problems = fresh_sheet(lst).reconcile()
    assert_problems(
        problems,
        must_mention=["list rating", "action head desync (rating)"],
        must_not_mention=["assignment 'Lasgun'", "fighter 'Bob':", "credits"],
    )


@pytest.mark.django_db
def test_meta_detects_stash_cache_tamper(healthy_list):
    lst, _, _ = healthy_list
    List.objects.filter(pk=lst.pk).update(stash_current=lst.stash_current + 7)
    problems = fresh_sheet(lst).reconcile()
    assert_problems(
        problems,
        must_mention=["list stash", "action head desync (stash)"],
        must_not_mention=["assignment 'Lasgun'", "fighter 'Bob':", "credits"],
    )


@pytest.mark.django_db
def test_meta_detects_credits_tamper(healthy_list):
    lst, _, _ = healthy_list
    List.objects.filter(pk=lst.pk).update(credits_current=lst.credits_current + 7)
    problems = fresh_sheet(lst).reconcile()
    assert_problems(
        problems,
        must_mention=["credits ledger", "action head desync (credits)"],
        must_not_mention=["assignment 'Lasgun'", "fighter 'Bob':", "list rating"],
    )


@pytest.mark.django_db
def test_meta_detects_action_delta_tamper(healthy_list):
    """A corrupted historical delta breaks the chain and the ledger."""
    lst, _, _ = healthy_list
    first_move = (
        ListAction.objects.filter(list=lst).exclude(rating_delta=0).earliest("created")
    )
    ListAction.objects.filter(pk=first_move.pk).update(
        rating_delta=first_move.rating_delta + 7
    )
    problems = fresh_sheet(lst).reconcile()
    assert_problems(
        problems,
        must_mention=["action chain break (rating)"],
        must_not_mention=["assignment 'Lasgun'", "credits ledger"],
    )


@pytest.mark.django_db
def test_meta_dirty_rows_are_not_problems(healthy_list):
    """Dirty is a legitimate transient state — surfaced, not a failure."""
    lst, fighter, _ = healthy_list
    ListFighter.objects.filter(pk=fighter.pk).update(
        dirty=True, rating_current=fighter.rating_current + 7
    )
    sheet = fresh_sheet(lst)
    assert "fighter 'Bob'" in "\n".join(sheet.dirty_rows)
    assert_problems(
        sheet.reconcile(), must_mention=[], must_not_mention=["fighter 'Bob':"]
    )


@pytest.mark.django_db
def test_meta_build_is_read_only(healthy_list):
    """build_balance_sheet issues no writes."""
    lst, _, _ = healthy_list
    lst.refresh_from_db()
    with CaptureQueriesContext(connection) as ctx:
        sheet = build_balance_sheet(lst)
        sheet.reconcile()
    writes = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].split(" ", 1)[0].upper() in ("INSERT", "UPDATE", "DELETE")
    ]
    assert writes == []


# ---------------------------------------------------------------------------
# Situation matrix
#
# Each cell drives a real app flow (handler or view) and applies the two-beat
# check. Known drift producers are pinned as strict xfails and flip to
# passing assertions in the phase that fixes them (see
# .claude/notes/cost-pinning-design.md §6).
# ---------------------------------------------------------------------------


@pytest.fixture
def campaign_list(user, make_list, campaign, content_source):
    """A campaign-mode list with a stash and a credit stake, fully chained.

    Subscribed to the axis pack when the pack side is active.
    """
    lst = make_list("War Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    content_source.subscribe(lst)
    stash = lst.ensure_stash()
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Starting stake",
        credits_delta=1000,
        update_credits=True,
    )
    lst.refresh_from_db()
    return lst, stash


def buy_accessory(user, lst, fighter, assignment, accessory):
    handle_accessory_purchase(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        accessory=accessory,
    )


# --- Healthy cells: list-building mode -------------------------------------


@pytest.mark.django_db
def test_matrix_buy_weapon_profile(healthy_list, user, gear):
    lst, fighter, assignment = healthy_list
    rating_before = fresh(lst).rating_current
    profile = gear.profile(assignment.content_equipment, name="Hotshot", cost=10)
    handle_weapon_profile_purchase(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        profile=profile,
    )
    # Reconciliation alone cannot see a bug where the write path and the
    # recompute path are identically blind (both book the wrong number and
    # agree) — so healthy cells also assert the actual booked movement.
    assert fresh(lst).rating_current == rating_before + 10
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_buy_accessory(healthy_list, user, gear):
    lst, fighter, assignment = healthy_list
    rating_before = fresh(lst).rating_current
    accessory = gear.accessory()
    buy_accessory(user, lst, fighter, assignment, accessory)
    assert fresh(lst).rating_current == rating_before + 8  # booked movement
    assert_reconciles(lst)


@pytest.mark.django_db
@pytest.mark.parametrize("side", ["catalog", "pack"])
def test_matrix_buy_upgrade(
    side, user, make_list, content_fighter, make_equipment, make_pack
):
    lst, fighter, assignment, equipment, source = build_weapon_list(
        side, user, make_list, content_fighter, make_equipment, make_pack
    )
    rating_before = fresh(lst).rating_current
    upgrade = source.register(
        ContentEquipmentUpgrade.objects.create(
            name="Extended mag", equipment=equipment, cost=12
        )
    )
    handle_equipment_upgrade(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        new_upgrades=[upgrade],
    )
    assert fresh(lst).rating_current == rating_before + 12  # booked movement
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_remove_accessory_from_fighter(healthy_list, user, gear):
    lst, fighter, assignment = healthy_list
    accessory = gear.accessory()
    buy_accessory(user, lst, fighter, assignment, accessory)
    rating_before = fresh(lst).rating_current
    handle_equipment_component_removal(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        component_type="accessory",
        component=accessory,
        request_refund=False,
    )
    assert fresh(lst).rating_current == rating_before - 8  # booked movement
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_remove_equipment(healthy_list, user):
    lst, fighter, assignment = healthy_list
    handle_equipment_removal(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        request_refund=False,
    )
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_total_override_set_and_clear(healthy_list, user):
    """Setting and clearing a fixed total reconciles when nothing else moves."""
    lst, fighter, assignment = healthy_list
    handle_equipment_cost_override(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        old_total_cost_override=None,
        new_total_cost_override=50,
    )
    assert_reconciles(lst)
    assignment.refresh_from_db()
    handle_equipment_cost_override(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        old_total_cost_override=50,
        new_total_cost_override=None,
    )
    assert_reconciles(lst)


# --- Healthy cells: campaign mode / stash lifecycle ------------------------


@pytest.mark.django_db
def test_matrix_buy_onto_stash(campaign_list, user, gear):
    lst, stash = campaign_list
    equipment = gear.equipment("Stash Gun", cost=50)
    buy_equipment(user, lst, stash, equipment)
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_reassign_plain_gear_between_fighters(
    campaign_list, user, content_fighter, gear
):
    lst, stash = campaign_list
    fighter_a = hire_fighter(user, lst, content_fighter, name="Alfa")
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    equipment = gear.equipment("Lasgun", cost=15)
    assignment = buy_equipment(user, lst, fighter_a, equipment)
    assert_reconciles(lst)

    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(fighter_a),
        to_fighter=fresh(fighter_b),
        assignment=fresh(assignment),
    )
    assert_reconciles(lst)

    assignment.refresh_from_db()
    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(fighter_b),
        to_fighter=fresh(stash),
        assignment=fresh(assignment),
    )
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_kill_fighter_with_plain_gear(
    campaign_list, user, content_fighter, gear
):
    """Death transfers undiscounted gear: same price in both contexts."""
    lst, stash = campaign_list
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    equipment = gear.equipment("Lasgun", cost=15)
    buy_equipment(user, lst, fighter, equipment)
    assert_reconciles(lst)

    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter))
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_repeat_death_plain_gear(campaign_list, user, content_fighter, gear):
    """Gear survives two deaths: kill A, re-equip to B, kill B."""
    lst, stash = campaign_list
    fighter_a = hire_fighter(user, lst, content_fighter, name="Alfa")
    equipment = gear.equipment("Lasgun", cost=15)
    buy_equipment(user, lst, fighter_a, equipment)
    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter_a))
    assert_reconciles(lst)

    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    stash_assignment = stash.listfighterequipmentassignment_set.get()
    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(stash),
        to_fighter=fresh(fighter_b),
        assignment=fresh(stash_assignment),
    )
    assert_reconciles(lst)

    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter_b))
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_sell_plain_gear_from_stash(campaign_list, user, client, gear):
    """Selling undiscounted stash gear: view prices catalog == cache."""
    lst, stash = campaign_list
    equipment = gear.equipment("Stash Gun", cost=50)
    assignment = buy_equipment(user, lst, stash, equipment)
    assert_reconciles(lst)

    client.force_login(user)
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.post(
        url + "?sell_assign=" + str(assignment.id),
        {
            "step": "selection",
            "0-price_method": "price_manual",
            "0-price_manual_value": "20",
        },
    )
    assert response.status_code == 302
    response = client.post(url, {"step": "confirm"})
    assert response.status_code == 302
    assert not ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).exists()
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_campaign_budget_grant_reconciles(
    user, make_list, make_campaign, content_fighter
):
    """Family-2 proof: a budget-funded gang's credits ledger reconciles."""
    lst = make_list("Budget Gang")
    hire_fighter(user, lst, content_fighter, name="Bob")
    campaign2 = make_campaign("Budget Campaign", status="in_progress", budget=1500)
    cloned, created = campaign2.add_list_to_campaign(fresh(lst), user=user)
    assert created
    cloned.refresh_from_db()
    assert cloned.credits_current > 0  # the grant actually happened
    assert_reconciles(cloned)


def build_weapon_list(
    side, user, make_list, content_fighter, make_equipment, make_pack
):
    """A list with one fighter and one weapon on an explicit axis side.

    For cells whose expectations differ per side (per-param xfail marks),
    which the axis fixture cannot express.
    """
    source = ContentSource(make_pack("Axis Pack") if side == "pack" else None)
    lst = make_list("Sidecar Gang")
    source.subscribe(lst)
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    equipment = source.register(make_equipment("Lasgun", cost=15))
    assignment = buy_equipment(user, lst, fighter, equipment)
    lst.refresh_from_db()
    return lst, fighter, assignment, equipment, source


# --- Content price change: the async window --------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("side", ["catalog", "pack"])
def test_matrix_content_price_change_window_is_visible(
    side, user, make_list, content_fighter, make_equipment, make_pack
):
    """Mid-window (sweep done, task not yet run), for PINNED gear: stable.

    Acquisition now writes receipts (Phase 7), so a recompute before the
    task lands reads the pinned amount — the books hold their value and
    reconcile cleanly; the correction arrives only WITH the task (which
    rewrites the amount and books the delta — the full-flow cell below).
    The pre-Phase-7 behaviour (recompute reveals an un-actioned change)
    remains real for legacy unpinned rows until the Phase 8 backfill and is
    pinned by the _legacy variant of this cell.
    """
    lst, fighter, assignment, equipment, _ = build_weapon_list(
        side, user, make_list, content_fighter, make_equipment, make_pack
    )
    rating_before = fresh(lst).rating_current
    equipment.cost = 25  # was 15
    equipment.save()

    # Dirty rows are surfaced, but dirtiness alone is not a problem.
    sheet = fresh_sheet(lst)
    assert sheet.dirty_rows
    assert sheet.reconcile() == []

    # A recompute before the task reads the receipt: nothing moves.
    force_recompute(lst)
    assert fresh(lst).rating_current == rating_before
    assert fresh_sheet(lst).reconcile() == []


@pytest.mark.django_db
@pytest.mark.parametrize("side", ["catalog", "pack"])
def test_matrix_content_price_change_window_is_visible_legacy(
    side, user, make_list, content_fighter, make_equipment, make_pack
):
    """Mid-window, for LEGACY (unpinned) rows: harness sees the gap.

    Pre-backfill rows reprice live on recompute, so between recompute and
    task the action chain legitimately trails the caches — the harness must
    show that, not hide it. Retires with the Phase 8 backfill.
    """
    lst, fighter, assignment, equipment, _ = build_weapon_list(
        side, user, make_list, content_fighter, make_equipment, make_pack
    )
    # Simulate a pre-Phase-7 row: strip the acquisition receipt.
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=None,
        pinned_base_state=PinState.UNPINNED,
    )
    equipment.cost = 25  # was 15
    equipment.save()

    # A recompute before the task lands reveals the un-actioned change.
    force_recompute(lst)
    problems = fresh_sheet(lst).reconcile()
    assert_problems(problems, must_mention=["action head desync (rating)"])


@pytest.mark.django_db
@pytest.mark.parametrize("side", ["catalog", "pack"])
def test_matrix_content_price_change_full_flow_reconciles(
    side, user, make_list, content_fighter, make_equipment, make_pack
):
    """After the async task creates the CONTENT_COST_CHANGE action: clean."""
    lst, fighter, assignment, equipment, _ = build_weapon_list(
        side, user, make_list, content_fighter, make_equipment, make_pack
    )

    before_snapshots = {str(lst.id): [lst.rating_current, lst.stash_current]}
    equipment.cost = 25
    equipment.save()

    ct = ContentType.objects.get_for_model(type(equipment))
    propagate_content_cost_change.func(ct.id, str(equipment.id), before_snapshots)
    assert_reconciles(lst)


# --- Legacy data: rows created outside the action system -------------------


@pytest.mark.django_db
def test_matrix_legacy_raw_fighter_detected_after_recompute(
    healthy_list, user, make_content_fighter, content_house
):
    """Pre-programme data (raw ORM, no action) surfaces as head desync.

    This is the harness working as designed: recomputing absorbs the raw
    fighter into the caches, and the missing action shows as a chain desync.
    """
    lst, _, _ = healthy_list
    cf = make_content_fighter(
        type="Legacy Ganger", category="GANGER", house=content_house, base_cost=60
    )
    ListFighter.objects.create(
        name="Shell-seeded", content_fighter=cf, list=lst, owner=user
    )

    force_recompute(lst)
    problems = fresh_sheet(lst).reconcile()
    assert_problems(problems, must_mention=["action head desync (rating)"])


# --- Known drift producers: strict xfails, one group per producer ----------


@pytest.mark.django_db
def test_matrix_p1_1925_accessory_onto_overridden_assignment(healthy_list, user, gear):
    """P1 (#1925), fixed in Phase 2: a component purchase onto a fixed-total
    assignment moves credits but not the book value — and reconciles."""
    lst, fighter, assignment = healthy_list
    handle_equipment_cost_override(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        old_total_cost_override=None,
        new_total_cost_override=50,
    )
    assert_reconciles(lst)  # clean before the purchase

    accessory = gear.accessory()
    buy_accessory(user, lst, fighter, assignment, accessory)
    assert_reconciles(lst)  # book value stays at the 50 override; credits moved


@pytest.mark.django_db
def test_matrix_p2_1826_kill_fighter_with_discounted_gear(
    campaign_list, user, make_content_fighter, content_house, gear
):
    """P2 (#1826), fixed in Phase 9 — the programme's headline bug.

    Gear bought at an equipment-list discount (5¢, catalog 15¢) keeps that
    price when its owner dies and it lands in the stash: the acquisition
    receipt travels with the clone, so the stash values it at 5¢ instead of
    re-pricing to catalog. The books reconcile through the death.
    """
    lst, stash = campaign_list
    cf = make_content_fighter(
        type="Scavvy", category="GANGER", house=content_house, base_cost=50
    )
    fighter = hire_fighter(user, lst, cf, name="Bob")
    equipment = gear.equipment("Lasgun", cost=15)
    ContentFighterEquipmentListItem.objects.create(
        fighter=cf, equipment=equipment, cost=5
    )
    buy_equipment(user, lst, fighter, equipment)
    assert_reconciles(lst)  # clean before the death

    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter))
    assert_reconciles(lst)  # receipt travels: stash caches 5 and recomputes to 5

    stash_assignment = stash.listfighterequipmentassignment_set.get()
    assert stash_assignment.cost_int() == 5  # discounted price held, not catalog 15


@pytest.mark.django_db
def test_matrix_p2_1826_full_lifecycle_prices_held(
    campaign_list, user, make_content_fighter, content_house, content_fighter, gear
):
    """The programme's headline scenario, end to end (#1826 §2.3).

    A buys a Lasgun at A's 5¢ equipment-list discount (catalog 15¢); A dies
    and it lands in the stash; B — who has no discount and would pay catalog —
    re-equips it from the stash; B buys a Scope in B's context; B dies too.
    The Lasgun holds 5¢ at every hop and the Scope holds its purchase value,
    on both catalog and pack content, with the books reconciling after each
    step (immediately and after a forced recompute).
    """
    lst, stash = campaign_list
    cf_a = make_content_fighter(
        type="Scavvy", category="GANGER", house=content_house, base_cost=50
    )
    lasgun = gear.equipment("Lasgun", cost=15)
    ContentFighterEquipmentListItem.objects.create(
        fighter=cf_a, equipment=lasgun, cost=5
    )

    # A buys the Lasgun at the 5¢ discount.
    fighter_a = hire_fighter(user, lst, cf_a, name="Alfa")
    assignment = buy_equipment(user, lst, fighter_a, lasgun)
    assert fresh(assignment).cost_int() == 5
    assert_reconciles(lst)

    # A dies: the Lasgun moves to the stash, keeping its 5¢ receipt (the stash
    # on its own would price it at catalog 15).
    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter_a))
    stash_assignment = stash.listfighterequipmentassignment_set.get()
    assert stash_assignment.cost_int() == 5
    assert_reconciles(lst)

    # B — no discount — re-equips the Lasgun from the stash. The pin holds: B
    # carries 5, not the 15 B's own context would compute.
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(stash),
        to_fighter=fresh(fighter_b),
        assignment=fresh(stash_assignment),
    )
    assert fresh(stash_assignment).cost_int() == 5
    assert_reconciles(lst)

    # B buys a Scope in B's context; it pins at its purchase price.
    scope = gear.accessory("Scope", cost=8)
    buy_accessory(user, lst, fighter_b, stash_assignment, scope)
    assert fresh(stash_assignment).cost_int() == 13  # 5 Lasgun + 8 Scope
    assert_reconciles(lst)

    # B dies too: the discounted Lasgun and the Scope both move to the stash at
    # their held values — a repeat death that stays price-neutral.
    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter_b))
    final = fresh(stash.listfighterequipmentassignment_set.get())
    assert final.cost_int() == 13  # 5 + 8, held through the second death
    assert_reconciles(lst)


@pytest.mark.django_db
def test_kill_conserves_equipment_value_no_phantom_wealth(
    campaign_list, user, make_content_fighter, content_house, gear
):
    """A death removes the fighter's whole cost from the rating and returns
    the equipment's HELD value to the stash — no more, no less.

    The #1826 bug was a phantom wealth gain: discounted gear re-pricing to
    catalog once it sat in the stash. Here the stash gains exactly the 5¢ the
    gear was worth, credits never move, and total wealth falls by only the
    fighter's base cost.
    """
    lst, stash = campaign_list
    cf = make_content_fighter(
        type="Scavvy", category="GANGER", house=content_house, base_cost=50
    )
    lasgun = gear.equipment("Lasgun", cost=15)
    ContentFighterEquipmentListItem.objects.create(fighter=cf, equipment=lasgun, cost=5)
    fighter = hire_fighter(user, lst, cf, name="Bob")
    buy_equipment(user, lst, fighter, lasgun)

    before = fresh(lst)
    rating_before = before.rating_current
    stash_before = before.stash_current
    credits_before = before.credits_current
    fighter_cost = fresh(fighter).cost_int()  # 50 base + 5 gear

    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter))

    after = fresh(lst)
    assert after.rating_current == rating_before - fighter_cost  # whole cost gone
    assert after.stash_current == stash_before + 5  # HELD value, not catalog 15
    assert after.credits_current == credits_before  # deaths never touch credits
    # Total wealth fell by exactly the base cost; the 5¢ gear was conserved.
    wealth_before = rating_before + stash_before + credits_before
    wealth_after = after.rating_current + after.stash_current + after.credits_current
    assert wealth_before - wealth_after == 50
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_p3_sell_overridden_gear_from_stash(campaign_list, user, client, gear):
    lst, stash = campaign_list
    equipment = gear.equipment("Stash Gun", cost=50)
    assignment = buy_equipment(user, lst, stash, equipment)
    handle_equipment_cost_override(
        user=user,
        lst=fresh(lst),
        fighter=fresh(stash),
        assignment=fresh(assignment),
        old_total_cost_override=None,
        new_total_cost_override=80,
    )
    assert_reconciles(lst)  # clean before the sale
    stash_before_sale = fresh(lst).stash_current

    client.force_login(user)
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.post(
        url + "?sell_assign=" + str(assignment.id),
        {
            "step": "selection",
            "0-price_method": "price_manual",
            "0-price_manual_value": "20",
        },
    )
    assert response.status_code == 302
    client.post(url, {"step": "confirm"})
    # P3, fixed in Phase 3: the sale books what the caches carry (the 80
    # override), not raw catalog — and the books reconcile.
    lst.refresh_from_db()
    assert stash_before_sale - lst.stash_current == 80
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_p4_remove_accessory_from_stash_gear(campaign_list, user, gear):
    lst, stash = campaign_list
    equipment = gear.equipment("Stash Gun", cost=50)
    assignment = buy_equipment(user, lst, stash, equipment)
    accessory = gear.accessory()
    buy_accessory(user, lst, stash, assignment, accessory)
    assert_reconciles(lst)  # clean before the removal
    stash_before_removal = fresh(lst).stash_current

    handle_equipment_component_removal(
        user=user,
        lst=fresh(lst),
        fighter=fresh(stash),
        assignment=fresh(assignment),
        component_type="accessory",
        component=accessory,
        request_refund=False,
    )
    # P4, fixed in Phase 3: the removal decrements the assignment and stash
    # fighter caches by the component's value, and the books reconcile.
    assert stash_before_removal - fresh(lst).stash_current == 8  # booked movement
    assert_reconciles(lst)


def _pin_for_clone(assignment):
    """Hand-write the pins Phase 7's acquisition choke point will produce:
    a base pin plus a pinned accessory through-row."""
    accessory = ContentWeaponAccessory.objects.create(name="Clone Scope", cost=8)
    assignment.weapon_accessories_field.add(accessory)
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=5, pinned_base_state=PinState.SOURCE
    )
    assignment.accessory_rows.update(pinned_amount=3, pin_state=PinState.SOURCE)


def _assert_pins_survived(clone, equipment):
    cloned = ListFighterEquipmentAssignment.objects.get(
        list_fighter__list=clone, content_equipment=equipment
    )
    assert cloned.pinned_base_amount == 5
    assert cloned.pinned_base_state == PinState.SOURCE
    assert cloned.accessory_rows.get().pinned_amount == 3


@pytest.mark.django_db
def test_matrix_clone_preserves_pins(user, make_list, content_fighter, make_equipment):
    lst = make_list("Clone Source")
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    equipment = make_equipment("Lasgun", cost=15)
    assignment = buy_equipment(user, lst, fighter, equipment)
    _pin_for_clone(assignment)

    clone = fresh(lst).clone(name="Clone Target")
    _assert_pins_survived(clone, equipment)


@pytest.mark.django_db
def test_matrix_campaign_start_clone_preserves_pins(
    user, make_list, content_fighter, make_equipment, campaign
):
    lst = make_list("Campaign Clone Source")
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    equipment = make_equipment("Lasgun", cost=15)
    assignment = buy_equipment(user, lst, fighter, equipment)
    _pin_for_clone(assignment)

    cloned, created = campaign.add_list_to_campaign(fresh(lst), user=user)
    assert created
    _assert_pins_survived(cloned, equipment)


@pytest.mark.django_db
@pytest.mark.parametrize("side", ["catalog", "pack"])
def test_new_gang_gear_is_pinned_end_to_end(
    side, user, make_list, content_fighter, make_equipment, make_pack, campaign
):
    """New gangs carry pins without any backfill. A fresh purchase pins at
    acquisition (Phase 7), and starting a campaign clones those pins in — so a
    gang built after Phase 7 shipped never relies on the estate backfill (or
    Phase 9's defensive kill-pin) for gear it bought itself. Proven end to end
    through the real purchase + campaign-start flows, on both content axes."""
    source = ContentSource(make_pack("New Gang Pack") if side == "pack" else None)
    lst = make_list("Fresh Gang")
    source.subscribe(lst)
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    lasgun = source.register(make_equipment("Lasgun", cost=15))

    assignment = buy_equipment(user, lst, fighter, lasgun)
    # The brand-new purchase is pinned at acquisition (no backfill involved).
    assert fresh(assignment).pinned_base_amount == 15
    assert fresh(assignment).pinned_base_state == PinState.CATALOG

    # Starting a campaign clones the gang in — the pins travel with it.
    cloned, created = campaign.add_list_to_campaign(fresh(lst), user=user)
    assert created
    clone_row = ListFighterEquipmentAssignment.objects.get(
        list_fighter__list=cloned, content_equipment=lasgun
    )
    assert clone_row.pinned_base_amount == 15
    assert_reconciles(cloned)


@pytest.mark.django_db
@pytest.mark.parametrize("side", ["catalog", "pack"])
def test_matrix_bare_accessory_post_is_inert(
    side, user, client, make_list, content_fighter, make_equipment, make_pack
):
    """A POST without accessory_id changes nothing (P5, fixed).

    The accessories-edit view used to carry a bare-form fallback that rewrote
    the whole accessory M2M with no cost propagation, no ListAction, and no
    credits — a live drift producer on the catalog side, and a silent no-op
    for pack accessories. The branch is deleted; a bare POST now just
    re-renders, the accessory survives on both sides, and the books agree.
    """
    lst, fighter, assignment, _, source = build_weapon_list(
        side, user, make_list, content_fighter, make_equipment, make_pack
    )
    accessory = source.register(
        ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    )
    buy_accessory(user, lst, fighter, assignment, accessory)
    assert_reconciles(lst)

    client.force_login(user)
    url = reverse(
        "core:list-fighter-weapon-accessories-edit",
        args=[lst.id, fighter.id, assignment.id],
    )
    response = client.post(url, {})  # no accessory_id
    assert response.status_code == 200  # falls through to the page render

    assert (
        ContentWeaponAccessory.objects.all_content()
        .filter(weapon_accessories=fresh(assignment))
        .exists()
    )
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_p6_reassign_discounted_gear_reprices(
    campaign_list,
    user,
    make_content_fighter,
    content_house,
    content_fighter,
    gear,
):
    lst, stash = campaign_list
    cf_a = make_content_fighter(
        type="Scavvy", category="GANGER", house=content_house, base_cost=50
    )
    fighter_a = hire_fighter(user, lst, cf_a, name="Alfa")
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    equipment = gear.equipment("Lasgun", cost=15)
    ContentFighterEquipmentListItem.objects.create(
        fighter=cf_a, equipment=equipment, cost=5
    )
    assignment = buy_equipment(user, lst, fighter_a, equipment)
    assert_reconciles(lst)  # clean before the move

    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(fighter_a),
        to_fighter=fresh(fighter_b),
        assignment=fresh(assignment),
    )
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_p6_repricing_telemetry_fires(
    campaign_list,
    user,
    make_content_fighter,
    content_house,
    content_fighter,
    gear,
    monkeypatch,
):
    """Reassigning PINNED gear is price-neutral: no reprice telemetry, the
    discounted price travels to a holder who would price it at catalog, and
    the books reconcile. This is the programme's signature outcome arriving
    for newly-acquired gear (acquisition pins since Phase 7); the legacy
    variant below keeps the pre-backfill repricing path covered.
    """
    from gyrinx.core.handlers.equipment import reassignment as reassignment_module

    events = []
    monkeypatch.setattr(
        reassignment_module,
        "track",
        lambda name, **kw: events.append((name, kw)),
    )

    lst, stash = campaign_list
    cf_a = make_content_fighter(
        type="Scavvy", category="GANGER", house=content_house, base_cost=50
    )
    fighter_a = hire_fighter(user, lst, cf_a, name="Alfa")
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    equipment = gear.equipment("Lasgun", cost=15)
    ContentFighterEquipmentListItem.objects.create(
        fighter=cf_a, equipment=equipment, cost=5
    )
    assignment = buy_equipment(user, lst, fighter_a, equipment)

    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(fighter_a),
        to_fighter=fresh(fighter_b),
        assignment=fresh(assignment),
    )

    reprice_events = [
        kw for name, kw in events if name == "equipment_cost_changed_on_reassignment"
    ]
    assert reprice_events == []
    assert fresh(assignment).cost_int() == 5  # the receipt travelled
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_p6_repricing_telemetry_fires_for_legacy_rows(
    campaign_list,
    user,
    make_content_fighter,
    content_house,
    content_fighter,
    gear,
    monkeypatch,
):
    """LEGACY (unpinned) gear still reprices on reassignment, and the
    telemetry fires with real values. Retires with the Phase 8 backfill."""
    from gyrinx.core.handlers.equipment import reassignment as reassignment_module

    events = []
    monkeypatch.setattr(
        reassignment_module,
        "track",
        lambda name, **kw: events.append((name, kw)),
    )

    lst, stash = campaign_list
    cf_a = make_content_fighter(
        type="Scavvy", category="GANGER", house=content_house, base_cost=50
    )
    fighter_a = hire_fighter(user, lst, cf_a, name="Alfa")
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    equipment = gear.equipment("Lasgun", cost=15)
    ContentFighterEquipmentListItem.objects.create(
        fighter=cf_a, equipment=equipment, cost=5
    )
    assignment = buy_equipment(user, lst, fighter_a, equipment)
    # Simulate a pre-Phase-7 row: strip the acquisition receipt.
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=None,
        pinned_base_state=PinState.UNPINNED,
    )

    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(fighter_a),
        to_fighter=fresh(fighter_b),
        assignment=fresh(assignment),
    )

    reprice_events = [
        kw for name, kw in events if name == "equipment_cost_changed_on_reassignment"
    ]
    assert len(reprice_events) == 1
    assert reprice_events[0]["cost_before"] == 5
    assert reprice_events[0]["cost_after"] == 15


@pytest.mark.django_db
def test_matrix_reassign_gear_with_pack_accessory(
    campaign_list, user, content_fighter, gear, pack
):
    """Pack-scoped accessories survive the reassignment repricing math.

    A plain refetch resolves accessories through the pack-excluding default
    manager, so a pack accessory would vanish from cost_after and the handler
    would book a phantom repricing. The handler (and this harness's fresh())
    must fetch with the same semantics the views use.
    """
    lst, stash = campaign_list
    lst.packs.add(pack)
    fighter_a = hire_fighter(user, lst, content_fighter, name="Alfa")
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    # Equipment rides the axis (so this cell is meaningfully doubled); the
    # accessory deliberately comes from its own separate pack.
    equipment = gear.equipment("Lasgun", cost=15)
    assignment = buy_equipment(user, lst, fighter_a, equipment)

    accessory = ContentWeaponAccessory.objects.create(name="Pack Scope", cost=8)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentWeaponAccessory),
        object_id=accessory.pk,
        owner=pack.owner,
    )
    buy_accessory(user, lst, fighter_a, assignment, accessory)
    assert_reconciles(lst)

    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(fighter_a),
        to_fighter=fresh(fighter_b),
        assignment=fresh(assignment),
    )
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_p8_reassign_gear_with_pack_profile(
    user, make_list, content_fighter, make_equipment, make_pack
):
    lst, fighter_a, assignment, equipment, source = build_weapon_list(
        "pack", user, make_list, content_fighter, make_equipment, make_pack
    )
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    profile = source.register(
        ContentWeaponProfile.objects.create(
            equipment=equipment, name="Hotshot", cost=10
        )
    )
    handle_weapon_profile_purchase(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter_a),
        assignment=fresh(assignment),
        profile=profile,
    )
    assert_reconciles(lst)  # clean before the move

    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(fighter_a),
        to_fighter=fresh(fighter_b),
        assignment=fresh(assignment),
    )
    # P8 (#1933), fixed in Phase 3: with_related_data() now prefetches all
    # three component types via all_content(), so the move prices the pack
    # profile on both ends and the books reconcile.
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_sell_pack_profile_from_stash(
    campaign_list, user, client, make_equipment, make_pack, make_weapon_profile
):
    """Selling an individual pack-scoped profile from stash gear works.

    The parts-only sale path used to look profiles up through the
    pack-excluding default manager, silently skipping pack profiles at both
    the selection and confirm steps; the handler's M2M .remove() no-opped for
    them too. The sale must actually remove the profile, book its resolved
    value out of the stash, and reconcile.
    """
    lst, stash = campaign_list
    source = ContentSource(make_pack("Profile Pack"))
    source.subscribe(lst)
    equipment = make_equipment("Stash Gun", cost=50)
    assignment = buy_equipment(user, lst, stash, equipment)
    profile = source.register(
        make_weapon_profile(equipment, name="Pack Hotshot", cost=10)
    )
    handle_weapon_profile_purchase(
        user=user,
        lst=fresh(lst),
        fighter=fresh(stash),
        assignment=fresh(assignment),
        profile=profile,
    )
    assert_reconciles(lst)
    stash_before_sale = fresh(lst).stash_current

    client.force_login(user)
    url = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, stash.id, assignment.id]
    )
    response = client.post(
        url + "?sell_profile=" + str(profile.id),
        {
            "step": "selection",
            "0-price_method": "price_manual",
            "0-price_manual_value": "5",
        },
    )
    assert response.status_code == 302
    client.post(url, {"step": "confirm"})

    # The profile actually sold: gone from the assignment, 10 booked out.
    assert not (
        ContentWeaponProfile.objects.all_content()
        .filter(weapon_profiles=fresh(assignment))
        .exists()
    )
    assert stash_before_sale - fresh(lst).stash_current == 10
    assert_reconciles(lst)


# --- #1949: pin-source attribution for the balance-sheet pricing tooltip -------


class _FakeRow:
    """Minimal stand-in for a pinned through-row (pin_state + amount + one FK)."""

    def __init__(self, pin_state, pinned_amount, fk=None):
        self.pin_state = pin_state
        self.pinned_amount = pinned_amount
        self.pinned_equipment_list_item = fk


def test_source_repr_per_pin_state():
    assert _source_repr(PinState.CATALOG, 15) == "Catalog price at acquisition (15¢)"
    assert _source_repr(PinState.DERIVED, 7) == "Derived price (7¢)"
    assert _source_repr(PinState.ORPHANED, 4).startswith("Frozen")
    # SOURCE resolves the attribution FK's string.
    assert _source_repr(PinState.SOURCE, 5, "Ganger — Sweep Lasgun") == (
        "Pinned to Ganger — Sweep Lasgun (5¢)"
    )
    assert _source_repr(PinState.SOURCE, 5) == "Pinned to an override price (5¢)"
    # Unpinned / absent amount → no receipt to describe.
    assert _source_repr(PinState.UNPINNED, None) == ""
    assert _source_repr(PinState.CATALOG, None) == ""


def test_rows_source_repr_single_row_resolves_fully():
    rows = [_FakeRow(PinState.SOURCE, 5, "Ganger — Sweep Lasgun")]
    assert _rows_source_repr(rows) == "Pinned to Ganger — Sweep Lasgun (5¢)"


def test_rows_source_repr_summarises_a_mix():
    rows = [
        _FakeRow(PinState.CATALOG, 5),
        _FakeRow(PinState.CATALOG, 5),
        _FakeRow(PinState.UNPINNED, None),
    ]
    out = _rows_source_repr(rows)
    assert "2× catalog" in out
    assert "1× live" in out


def test_rows_source_repr_all_unpinned_is_empty():
    assert _rows_source_repr([_FakeRow(PinState.UNPINNED, None)]) == ""


@pytest.mark.django_db
def test_balance_sheet_populates_pinned_line_source_repr(
    user, make_list, content_fighter, make_equipment
):
    """A purchased line pins at acquisition, so its base ComponentLine carries a
    non-empty, amount-bearing source_repr for the tooltip; an unpinned line
    carries none."""
    lst = make_list("Sheet Gang")
    fighter = hire_fighter(user, lst, content_fighter)
    buy_equipment(user, lst, fighter, make_equipment("Lasgun", cost=15))

    sheet = fresh_sheet(lst)
    fb = next(f for f in sheet.fighters if f.fighter_id == fighter.id)
    base = next(line for line in fb.assignments[0].lines if line.kind == "base")

    if base.pricing in ("pinned", "user_override"):
        assert base.source_repr and base.source_repr.endswith("¢)")
    else:
        assert base.source_repr == ""
