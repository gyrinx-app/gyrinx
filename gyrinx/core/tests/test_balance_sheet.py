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
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.core.cost.balance_sheet import build_balance_sheet
from gyrinx.core.handlers.equipment.purchase import handle_equipment_purchase
from gyrinx.core.handlers.fighter.hire_clone import handle_fighter_hire
from gyrinx.core.models.action import ListAction
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)

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


@pytest.fixture
def healthy_list(user, make_list, content_fighter, make_equipment):
    """A list built entirely through real flows: one fighter, one weapon."""
    lst = make_list("Balance Gang")
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    equipment = make_equipment("Lasgun", cost=15)
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
# check. Known drift producers are pinned as strict xfails, grouped P1-P6;
# they flip to passing in the phase that fixes them (see
# .claude/notes/cost-pinning-design.md §6).
# ---------------------------------------------------------------------------

from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.urls import reverse  # noqa: E402

from gyrinx.content.models import (  # noqa: E402
    ContentEquipmentUpgrade,
    ContentFighterEquipmentListItem,
    ContentWeaponAccessory,
)
from gyrinx.core.handlers.equipment.cost_override import (  # noqa: E402
    handle_equipment_cost_override,
)
from gyrinx.core.handlers.equipment.purchase import (  # noqa: E402
    handle_accessory_purchase,
    handle_equipment_upgrade,
    handle_weapon_profile_purchase,
)
from gyrinx.core.handlers.equipment.reassignment import (  # noqa: E402
    handle_equipment_reassignment,
)
from gyrinx.core.handlers.equipment.removal import (  # noqa: E402
    handle_equipment_component_removal,
    handle_equipment_removal,
)
from gyrinx.core.handlers.fighter.kill import handle_fighter_kill  # noqa: E402
from gyrinx.core.models.action import ListActionType  # noqa: E402
from gyrinx.core.tasks import propagate_content_cost_change  # noqa: E402


@pytest.fixture
def campaign_list(user, make_list, campaign):
    """A campaign-mode list with a stash and a credit stake, fully chained."""
    lst = make_list("War Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
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
def test_matrix_buy_weapon_profile(healthy_list, user, make_weapon_profile):
    lst, fighter, assignment = healthy_list
    profile = make_weapon_profile(assignment.content_equipment, name="Hotshot", cost=10)
    handle_weapon_profile_purchase(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        profile=profile,
    )
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_buy_accessory(healthy_list, user):
    lst, fighter, assignment = healthy_list
    accessory = ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    buy_accessory(user, lst, fighter, assignment, accessory)
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_buy_upgrade(healthy_list, user):
    lst, fighter, assignment = healthy_list
    upgrade = ContentEquipmentUpgrade.objects.create(
        name="Extended mag", equipment=assignment.content_equipment, cost=12
    )
    handle_equipment_upgrade(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        new_upgrades=[upgrade],
    )
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_remove_accessory_from_fighter(healthy_list, user):
    lst, fighter, assignment = healthy_list
    accessory = ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    buy_accessory(user, lst, fighter, assignment, accessory)
    handle_equipment_component_removal(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        component_type="accessory",
        component=accessory,
        request_refund=False,
    )
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
def test_matrix_buy_onto_stash(campaign_list, user, make_equipment):
    lst, stash = campaign_list
    equipment = make_equipment("Stash Gun", cost=50)
    buy_equipment(user, lst, stash, equipment)
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_reassign_catalog_gear_between_fighters(
    campaign_list, user, content_fighter, make_equipment
):
    lst, stash = campaign_list
    fighter_a = hire_fighter(user, lst, content_fighter, name="Alfa")
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    equipment = make_equipment("Lasgun", cost=15)
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
def test_matrix_kill_fighter_with_catalog_gear(
    campaign_list, user, content_fighter, make_equipment
):
    """Death transfers catalog-priced gear: same price in both contexts."""
    lst, stash = campaign_list
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    equipment = make_equipment("Lasgun", cost=15)
    buy_equipment(user, lst, fighter, equipment)
    assert_reconciles(lst)

    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter))
    assert_reconciles(lst)


@pytest.mark.django_db
def test_matrix_repeat_death_catalog_gear(
    campaign_list, user, content_fighter, make_equipment
):
    """Gear survives two deaths: kill A, re-equip to B, kill B."""
    lst, stash = campaign_list
    fighter_a = hire_fighter(user, lst, content_fighter, name="Alfa")
    equipment = make_equipment("Lasgun", cost=15)
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
def test_matrix_sell_catalog_gear_from_stash(
    campaign_list, user, client, make_equipment
):
    """Selling catalog-priced stash gear: view prices catalog == cache."""
    lst, stash = campaign_list
    equipment = make_equipment("Stash Gun", cost=50)
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


# --- Content price change: the async window --------------------------------


@pytest.mark.django_db
def test_matrix_content_price_change_window_is_visible(healthy_list):
    """Mid-window (sweep done, task not yet run): harness sees the gap.

    A content price change marks caches dirty synchronously; the audit action
    lands later via the async task. Between recompute and task, the action
    chain legitimately trails the caches — the harness must show that, not
    hide it.
    """
    lst, fighter, assignment = healthy_list
    equipment = assignment.content_equipment
    equipment.cost = 25  # was 15
    equipment.save()

    # Dirty rows are surfaced, but dirtiness alone is not a problem.
    sheet = fresh_sheet(lst)
    assert sheet.dirty_rows
    assert sheet.reconcile() == []

    # A recompute before the task lands reveals the un-actioned change.
    force_recompute(lst)
    problems = fresh_sheet(lst).reconcile()
    assert_problems(problems, must_mention=["action head desync (rating)"])


@pytest.mark.django_db
def test_matrix_content_price_change_full_flow_reconciles(healthy_list):
    """After the async task creates the CONTENT_COST_CHANGE action: clean."""
    lst, fighter, assignment = healthy_list
    equipment = assignment.content_equipment

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
def test_matrix_p1_1925_accessory_onto_overridden_assignment(healthy_list, user):
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

    accessory = ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    buy_accessory(user, lst, fighter, assignment, accessory)
    assert_reconciles(lst)  # book value stays at the 50 override; credits moved


@pytest.mark.django_db
@pytest.mark.xfail(
    strict=True,
    reason="P2 (#1826): kill-transfer values gear in the dying fighter's "
    "context; the stash re-prices it at catalog; fixed by pinning (Phase 9)",
)
def test_matrix_p2_1826_kill_fighter_with_discounted_gear(
    campaign_list, user, make_content_fighter, content_house, make_equipment
):
    lst, stash = campaign_list
    cf = make_content_fighter(
        type="Scavvy", category="GANGER", house=content_house, base_cost=50
    )
    fighter = hire_fighter(user, lst, cf, name="Bob")
    equipment = make_equipment("Lasgun", cost=15)
    ContentFighterEquipmentListItem.objects.create(
        fighter=cf, equipment=equipment, cost=5
    )
    buy_equipment(user, lst, fighter, equipment)
    assert_reconciles(lst)  # clean before the death

    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter))
    assert_reconciles(lst)  # FAILS: stash cache +5, stash recomputes to 15


@pytest.mark.django_db
@pytest.mark.xfail(
    strict=True,
    reason="P3: the sale flow prices lines at raw catalog cost, ignoring "
    "overrides; cache decrements diverge from cost_int(); fixed in Phase 3",
)
def test_matrix_p3_sell_overridden_gear_from_stash(
    campaign_list, user, client, make_equipment
):
    lst, stash = campaign_list
    equipment = make_equipment("Stash Gun", cost=50)
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
    assert_reconciles(lst)  # FAILS: sale removed 50 (catalog) from a cache holding 80


@pytest.mark.django_db
@pytest.mark.xfail(
    strict=True,
    reason="P4: stash component removal propagates rating_delta (0 for "
    "stash) instead of the component's value; fixed in Phase 3",
)
def test_matrix_p4_remove_accessory_from_stash_gear(
    campaign_list, user, make_equipment
):
    lst, stash = campaign_list
    equipment = make_equipment("Stash Gun", cost=50)
    assignment = buy_equipment(user, lst, stash, equipment)
    accessory = ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    buy_accessory(user, lst, stash, assignment, accessory)
    assert_reconciles(lst)  # clean before the removal

    handle_equipment_component_removal(
        user=user,
        lst=fresh(lst),
        fighter=fresh(stash),
        assignment=fresh(assignment),
        component_type="accessory",
        component=accessory,
        request_refund=False,
    )
    assert_reconciles(lst)  # FAILS: assignment/fighter caches keep the 8


@pytest.mark.django_db
@pytest.mark.xfail(
    strict=True,
    reason="P5: the accessories edit view's bare-form branch rewrites the "
    "M2M with no propagation, action, or credits; removed in Phase 3",
)
def test_matrix_p5_bare_form_accessory_removal(healthy_list, user, client):
    lst, fighter, assignment = healthy_list
    accessory = ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    buy_accessory(user, lst, fighter, assignment, accessory)
    assert_reconciles(lst)  # clean before the bare POST

    client.force_login(user)
    url = reverse(
        "core:list-fighter-weapon-accessories-edit",
        args=[lst.id, fighter.id, assignment.id],
    )
    response = client.post(url, {})  # no accessory_id -> bare form branch
    assert response.status_code == 302
    assert_reconciles(lst)  # FAILS: M2M cleared, caches and ledger untouched


@pytest.mark.django_db
def test_matrix_p6_reassign_discounted_gear_reprices(
    campaign_list,
    user,
    make_content_fighter,
    content_house,
    content_fighter,
    make_equipment,
):
    lst, stash = campaign_list
    cf_a = make_content_fighter(
        type="Scavvy", category="GANGER", house=content_house, base_cost=50
    )
    fighter_a = hire_fighter(user, lst, cf_a, name="Alfa")
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")
    equipment = make_equipment("Lasgun", cost=15)
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
    assert_reconciles(lst)  # FAILS: moved at 5, B's context recomputes to 15


@pytest.mark.django_db
def test_matrix_p6_repricing_telemetry_fires(
    campaign_list,
    user,
    make_content_fighter,
    content_house,
    content_fighter,
    make_equipment,
    monkeypatch,
):
    """The cost-changed-on-reassignment telemetry fires with real values."""
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
    equipment = make_equipment("Lasgun", cost=15)
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
    assert len(reprice_events) == 1
    assert reprice_events[0]["cost_before"] == 5
    assert reprice_events[0]["cost_after"] == 15
