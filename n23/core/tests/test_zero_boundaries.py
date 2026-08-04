"""Zero-boundary cells: negative costs, refunds, and values crossing zero.

The cost system has THREE deliberately different behaviours at zero, and
each must hold exactly — a value goes negative only where we are absolutely
confident negative is the right answer:

1. **Credits never go negative.** Overdraft is a hard ValidationError, not a
   clamp. Negative *costs* are legitimate credit gains (Goliath
   gene-smithing), refunds are gains — both increase credits.
2. **List rating/stash never go negative** (positive-only DB fields) — and
   when a computed total IS negative, the zero-floor must be LOUD: the
   balance sheet flags the discrepancy and reconcile flags the clamp.
   Silent clamping eats value and breaks the ledger invisibly.
3. **Fighter/assignment caches and pinned amounts go negative freely** when
   content dictates — they are plain integers carrying content truth, and
   the books must track them exactly through zero in both directions.
"""

import pytest
from django.core.exceptions import ValidationError

from n23.content.models import ContentEquipmentUpgrade
from n23.core.cost.reconcile import reconcile_list
from n23.core.handlers.equipment.purchase import handle_equipment_upgrade
from n23.core.handlers.equipment.removal import handle_equipment_removal
from n23.core.models.action import ListActionType
from n23.core.models.list import (
    List,
    ListFighterEquipmentAssignment,
    PinState,
)
from n23.core.tests.test_balance_sheet import (
    assert_reconciles,
    buy_equipment,
    fresh,
    fresh_sheet,
    hire_fighter,
)


@pytest.fixture
def gang(user, make_list, content_fighter, campaign):
    """Campaign gang with a modest 200¢ stake — small enough that boundary
    cells can reach zero without contortions."""
    lst = make_list("Boundary Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Stake",
        credits_delta=200,
    )
    lst.apply_credit_delta(200)
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")  # 100¢
    return fresh(lst), fighter


# --- Credits: gains are real, overdraft is impossible -------------------------


@pytest.mark.django_db
def test_negative_cost_gear_gains_credits_and_reconciles(gang, user, make_equipment):
    """Negative-cost content (the gene-smithing pattern) pays the gang:
    credits go UP, the fighter gets cheaper, the receipt records the
    negative amount, and the books reconcile."""
    lst, fighter = gang
    credits_before = lst.credits_current
    rating_before = lst.rating_current

    drawback = make_equipment("Drawback", cost=-10)
    assignment = buy_equipment(user, lst, fighter, drawback)

    rf = fresh(lst)
    assert rf.credits_current == credits_before + 10
    assert rf.rating_current == rating_before - 10
    row = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
    assert (row.pinned_base_amount, row.pinned_base_state) == (-10, PinState.CATALOG)
    assert_reconciles(lst)


@pytest.mark.django_db
def test_credits_reach_exactly_zero_then_overdraft_hard_fails(
    gang, user, make_equipment
):
    """Spending down to exactly zero is fine; one more credit is a hard
    ValidationError — never a negative balance, never a clamp."""
    lst, fighter = gang
    exact = make_equipment("Exact Gun", cost=lst.credits_current)
    buy_equipment(user, lst, fighter, exact)
    assert fresh(lst).credits_current == 0
    assert_reconciles(lst)

    # The overdraft attempt: the handler refuses atomically. (The real view
    # deletes the form-created assignment on this error; mimic that.)
    too_much = make_equipment("One More Gun", cost=1)
    with pytest.raises(ValidationError):
        buy_equipment(user, fresh(lst), fresh(fighter), too_much)
    ListFighterEquipmentAssignment.objects.filter(content_equipment=too_much).delete()

    assert fresh(lst).credits_current == 0  # not -1, not clamped: untouched
    assert_reconciles(lst)


@pytest.mark.django_db
def test_removal_refund_is_a_gain_and_reconciles(gang, user, make_equipment):
    lst, fighter = gang
    gun = make_equipment("Refund Gun", cost=30)
    assignment = buy_equipment(user, lst, fighter, gun)
    credits_after_buy = fresh(lst).credits_current

    handle_equipment_removal(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        request_refund=True,
    )

    assert fresh(lst).credits_current == credits_after_buy + 30
    assert_reconciles(lst)


@pytest.mark.django_db
def test_upgrade_removal_gives_no_refund_by_design(gang, user, make_equipment):
    """Removing upgrades is deliberately NOT a refund: the handler moves
    credits on downgrade only when the NEW upgrade set itself is
    negative-cost (gaining from negative upgrades). Rating drops by the
    removed value, credits stay put, and the books reconcile — the value
    leaves the gang's worth without entering its purse. Pinned here so a
    future change to that rule is a conscious one."""
    lst, fighter = gang
    gun = make_equipment("Upgrade Gun", cost=10)
    assignment = buy_equipment(user, lst, fighter, gun)
    dear = ContentEquipmentUpgrade.objects.create(
        equipment=gun, name="Dear", position=0, cost=30
    )
    handle_equipment_upgrade(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        new_upgrades=[dear],
    )
    credits_with_dear = fresh(lst).credits_current
    rating_with_dear = fresh(lst).rating_current
    assert_reconciles(lst)

    handle_equipment_upgrade(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        new_upgrades=[],
    )
    rf = fresh(lst)
    assert rf.credits_current == credits_with_dear  # no refund, by design
    assert rf.rating_current == rating_with_dear - 30
    assert_reconciles(lst)


# --- List caches: the zero floor must be LOUD ---------------------------------


@pytest.mark.django_db
def test_fighter_crossing_zero_floors_list_rating_loudly(
    gang, user, make_content_fighter, content_house, make_equipment
):
    """A fighter whose gear drags their total negative: the fighter cache
    carries the true negative (plain integer — content truth), the list
    cache floors at zero (positive-only field), and NOTHING is silent —
    the purchase-time clamp surfaces as a harness problem and reconcile
    flags the clamp."""
    lst, _ = gang
    cheap_cf = make_content_fighter(
        type="Cheap Mook", category="GANGER", house=content_house, base_cost=5
    )
    mook = hire_fighter(user, lst, cheap_cf, name="Mook")
    assert_reconciles(lst)

    # Two big drawbacks drag the whole LIST total below zero:
    # 100 (Bob) + 5 (Mook) - 200 = -95.
    drawback = make_equipment("Massive Drawback", cost=-100)
    buy_equipment(user, lst, mook, drawback)
    buy_equipment(user, lst, fresh(mook), drawback)

    # The fighter's own cache holds the true negative...
    assert fresh(mook).cost_int() == 5 - 200
    # ...the list floors at zero (the DB field cannot hold a negative)...
    assert fresh(lst).rating_current == 0
    # ...and the floor is LOUD, not silent: the harness reports the gap.
    assert fresh_sheet(lst).reconcile() != []

    # Reconcile trues up what it can and flags the fired clamp explicitly.
    result = reconcile_list(lst, user=user)
    assert result.clamped is True
    assert fresh(lst).rating_current == 0  # still floored, still visible


# --- Pinned amounts: negative is content truth, crossing zero tracks exactly ---


@pytest.mark.django_db
def test_receipt_crossing_zero_upward_books_exactly(gang, user, make_equipment):
    """A negative-cost item corrected to a positive price: the receipt
    crosses zero, and the books move by exactly the correction."""
    from n23.content.models.signal_handlers import (
        _create_content_cost_change_actions,
    )

    lst, fighter = gang
    drawback = make_equipment("Volatile Drawback", cost=-10)
    assignment = buy_equipment(user, lst, fighter, drawback)
    assert_reconciles(lst)
    credits_before = fresh(lst).credits_current

    drawback.cost = "5"  # -10 -> +5: crosses zero
    drawback.save()
    _create_content_cost_change_actions(drawback, old_cost=-10)

    row = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
    assert row.pinned_base_amount == 5
    assert fresh(lst).credits_current == credits_before - 15  # charged exactly
    assert_reconciles(lst)


@pytest.mark.django_db
def test_single_stack_receipt_delta_crossing_zero(gang, user, make_equipment):
    """A cumulative-stack receipt driven negative by a rung correction:
    the delta applies exactly, the negative amount matches what live
    resolution would compute, and the books reconcile."""
    from n23.content.models.signal_handlers import (
        _create_content_cost_change_actions,
    )

    lst, fighter = gang
    gun = make_equipment("Stack Gun", cost=10)
    assignment = buy_equipment(user, lst, fighter, gun)
    rung0 = ContentEquipmentUpgrade.objects.create(
        equipment=gun, name="Rung 0", position=0, cost=5
    )
    # Through the real flow: books the +5 and writes the DERIVED receipt.
    handle_equipment_upgrade(
        user=user,
        lst=fresh(lst),
        fighter=fresh(fighter),
        assignment=fresh(assignment),
        new_upgrades=[rung0],
    )
    row = assignment.upgrade_rows.get()
    assert (row.pinned_amount, row.pin_state) == (5, PinState.DERIVED)

    rung0.cost = -3  # 5 -> -3: the receipt crosses zero by delta
    rung0.save()
    _create_content_cost_change_actions(rung0, old_cost=5)

    row = assignment.upgrade_rows.get()
    assert row.pinned_amount == -3
    # The receipt agrees with what live resolution would now say.
    live = ListFighterEquipmentAssignment.objects.with_related_data().get(
        pk=assignment.pk
    )
    assert live._upgrade_cost_with_override(rung0) == -3  # reads the pin
    assert_reconciles(lst)


# --- The delta-apply clamp: visible, never silent -------------------------------


@pytest.mark.django_db
def test_action_delta_clamp_is_visible_to_the_harness(gang, user):
    """The list-cache writer floors at zero (max(0, current + delta)).
    If a movement would push rating negative, the lost remainder MUST
    surface as a harness problem — this cell pins that the clamp can never
    eat value silently. The writer is the propagation layer; the action
    records the same over-large delta."""
    from n23.core.cost.propagation import propagate_to_list

    lst, fighter = gang
    rating = fresh(lst).rating_current
    lst = fresh(lst)
    propagate_to_list(lst, rating_delta=-(rating + 50))  # would land at -50
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        description="Synthetic over-refund (boundary probe)",
        rating_delta=-(rating + 50),
        rating_before=rating,
    )

    assert fresh(lst).rating_current == 0  # floored, not negative
    problems = fresh_sheet(lst).reconcile()
    assert problems != []  # the eaten 50¢ is visible, not silent
    assert any("head desync (rating)" in p for p in problems)
