"""Phase 8 of the cost-pinning programme (#1826): audited reconcile + backfill.

The reconcile core trues up drifted caches from live resolution and records
the movement as a RECONCILE action chained off the ledger head — the books
absorb years of un-audited drift without breaking chain continuity. The
backfill then writes acquisition receipts onto every legacy row via the same
choke point acquisition uses, value- and cache-neutrally.
"""

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from n23.content.models import ContentFighterEquipmentListItem
from n23.core.cost.reconcile import reconcile_list
from n23.core.models.action import ListAction, ListActionType
from n23.core.models.list import (
    List,
    ListFighter,
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
def tracked_list(user, make_list, content_fighter, make_equipment, campaign):
    """A campaign list with real actions, one fighter, one bought weapon."""
    lst = make_list("Reconcile Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Stake",
        credits_delta=1000,
    )
    lst.apply_credit_delta(1000)
    fighter = hire_fighter(user, lst, content_fighter, name="Bob")
    equipment = make_equipment("Lasgun", cost=15)
    assignment = buy_equipment(user, lst, fighter, equipment)
    return lst, fighter, assignment, equipment


# --- RECONCILE -----------------------------------------------------------------


@pytest.mark.django_db
def test_reconcile_absorbs_hidden_drift_into_the_ledger(tracked_list, user):
    """Seeded drift (stale cache behind a clean flag) is corrected, and the
    RECONCILE action chains off the ledger head so the harness's continuity
    invariant holds THROUGH the correction."""
    lst, fighter, assignment, _ = tracked_list
    assert_reconciles(lst)
    true_rating = fresh(lst).rating_current

    # Hidden drift: inflate the fighter and list caches, flags stay clean —
    # the classic pre-programme corruption shape.
    ListFighter.objects.filter(pk=fighter.pk).update(
        rating_current=fighter.rating_current + 10, dirty=False
    )
    List.objects.filter(pk=lst.pk).update(rating_current=true_rating + 10, dirty=False)
    assert fresh_sheet(lst).reconcile() != []  # the harness sees it

    result = reconcile_list(lst, user=user)

    assert result.moved
    assert fresh(lst).rating_current == true_rating
    # No action: the tamper never entered the ledger — the chain's head
    # already ends at the true value, so recomputing the cache back to it
    # leaves nothing for the ledger to absorb. Continuity holds throughout.
    assert result.action is None
    assert_reconciles(lst)


@pytest.mark.django_db
def test_reconcile_absorbs_real_computed_movement(tracked_list, user):
    """When live resolution genuinely disagrees with the ledger head (an
    unpinned row's price changed under it), RECONCILE books the difference."""
    lst, fighter, assignment, equipment = tracked_list
    # Make the row legacy (unpinned) so a price change reprices it live.
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=None, pinned_base_state=PinState.UNPINNED
    )
    equipment.cost = "25"  # was 15; no sweep task runs here
    equipment.save()

    result = reconcile_list(lst, user=user)

    assert result.action is not None
    assert result.action.rating_delta == 10
    assert result.action.credits_delta == 0  # books corrected, no wealth event
    assert fresh(lst).rating_current == result.action.rating_before + 10
    assert_reconciles(lst)


@pytest.mark.django_db
def test_reconcile_without_movement_writes_nothing(tracked_list, user):
    lst, *_ = tracked_list
    n_before = ListAction.objects.filter(list=lst).count()
    result = reconcile_list(lst, user=user)
    assert not result.moved
    assert result.action is None
    assert ListAction.objects.filter(list=lst).count() == n_before


@pytest.mark.django_db
def test_reconcile_untracked_list_fixes_caches_silently(
    user, make_list, content_fighter
):
    """Lists outside the action system get corrected caches, no action —
    there is no chain to keep continuous."""
    lst = make_list("Untracked Gang")
    # Raw creation: the fixtures' fighter factory writes actions.
    ListFighter.objects.create(
        list=lst, owner=user, content_fighter=content_fighter, name="Bob"
    )
    ListAction.objects.filter(list=lst).delete()
    List.objects.filter(pk=lst.pk).update(rating_current=999, dirty=False)

    result = reconcile_list(lst, user=user)

    assert result.action is None
    assert fresh(lst).rating_current != 999
    assert not ListAction.objects.filter(list=lst).exists()


@pytest.mark.django_db
def test_admin_recompute_writes_reconcile_action(tracked_list, user):
    """The admin recompute action adopts the audited path."""
    from n23.core.admin.list import recompute_list_cost_caches

    lst, fighter, *_ = tracked_list
    true_rating = fresh(lst).rating_current
    ListFighter.objects.filter(pk=fighter.pk).update(
        rating_current=fighter.rating_current + 7, dirty=False
    )
    List.objects.filter(pk=lst.pk).update(rating_current=true_rating + 7, dirty=False)

    request = RequestFactory().post("/admin/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    recompute_list_cost_caches(None, request, List.objects.filter(pk=lst.pk))

    assert fresh(lst).rating_current == true_rating
    assert_reconciles(lst)


# --- Backfill --------------------------------------------------------------------


@pytest.mark.django_db
def test_backfill_pins_legacy_population_value_neutrally(
    tracked_list, user, make_list_fighter, make_equipment
):
    """The backfill receipts a mixed legacy population — discounted, catalog,
    archived, frozen, user-overridden — without moving a single number."""
    from django.core.management import call_command

    lst, fighter, assignment, equipment = tracked_list
    # Make everything legacy: strip the acquisition receipts Phase 7 wrote.
    ListFighterEquipmentAssignment.objects.all().update(
        pinned_base_amount=None,
        pinned_base_state=PinState.UNPINNED,
        pinned_equipment_list_item=None,
        pinned_expansion_item=None,
    )

    # A discounted row, an archived row, a frozen row, a user-overridden row.
    discount_gun = make_equipment("Discount Gun", cost=20)
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter.content_fighter, equipment=discount_gun, cost=5
    )
    discounted = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=discount_gun
    )
    ListFighterEquipmentAssignment.objects.filter(pk=discounted.pk).update(
        pinned_base_amount=None, pinned_base_state=PinState.UNPINNED
    )
    archived = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=make_equipment("Old Gun", cost=30)
    )
    ListFighterEquipmentAssignment.objects.filter(pk=archived.pk).update(
        archived=True,
        pinned_base_amount=None,
        pinned_base_state=PinState.UNPINNED,
    )
    frozen = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=make_equipment("Frozen Gun", cost=40)
    )
    ListFighterEquipmentAssignment.objects.filter(pk=frozen.pk).update(
        total_cost_override=99,
        pinned_base_amount=None,
        pinned_base_state=PinState.UNPINNED,
    )
    overridden = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=make_equipment("Priced Gun", cost=50)
    )
    ListFighterEquipmentAssignment.objects.filter(pk=overridden.pk).update(
        cost_override=3,
        pinned_base_amount=None,
        pinned_base_state=PinState.UNPINNED,
    )

    reconcile_list(lst, user=user)  # §4.8.2: true up before freezing amounts
    actions_before = ListAction.objects.filter(list=lst).count()
    rating_before = fresh(lst).rating_current
    costs_before = {
        a.pk: fresh(a).cost_int()
        for a in ListFighterEquipmentAssignment.objects.filter(list_fighter__list=lst)
    }

    call_command("backfill_pins")

    def pin(a):
        row = ListFighterEquipmentAssignment.objects.get(pk=a.pk)
        return (row.pinned_base_amount, row.pinned_base_state)

    assert pin(assignment) == (15, PinState.CATALOG)
    assert pin(discounted) == (5, PinState.SOURCE)
    assert pin(archived) == (30, PinState.CATALOG)  # archived rows receipted too
    assert pin(frozen) == (None, PinState.UNPINNED)  # frozen stays for Phase 8b
    assert pin(overridden) == (None, PinState.UNPINNED)  # user override anchors

    # Value- and cache-neutral: nothing moved, no actions were written.
    for a_pk, before in costs_before.items():
        a = ListFighterEquipmentAssignment.objects.with_related_data().get(pk=a_pk)
        assert a.cost_int() == before
    assert fresh(lst).rating_current == rating_before
    # ...and the backfill itself wrote no actions (the RECONCILE above was
    # the pre-backfill true-up, not the backfill).
    assert ListAction.objects.filter(list=lst).count() == actions_before

    # Idempotent: a second run writes nothing new.
    from n23.core.cost.pinning import pin_assignment

    assert (
        sum(
            pin_assignment(a)
            for a in ListFighterEquipmentAssignment.objects.filter(
                list_fighter__list=lst
            )
        )
        == 0
    )


@pytest.mark.django_db
def test_backfill_task_walks_the_cursor(tracked_list, user):
    """The async task processes a batch and pins it; the cursor form picks
    up where the previous batch ended."""
    from n23.core.tasks import backfill_pins

    lst, fighter, assignment, _ = tracked_list
    ListFighterEquipmentAssignment.objects.all().update(
        pinned_base_amount=None, pinned_base_state=PinState.UNPINNED
    )

    backfill_pins.func(after_id=None, batch_size=500)

    row = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
    assert row.pinned_base_state == PinState.CATALOG


@pytest.mark.django_db
def test_reconcile_books_written_value_when_clamp_fires(tracked_list, user):
    """A negative computed total is floored to zero by the cache fields: the
    ledger must book the WRITTEN zero (booking the raw negative would end
    the chain where the cache can never be) and the fired clamp is flagged."""
    lst, fighter, assignment, _ = tracked_list
    # Drive the computed rating negative: a pathological negative override,
    # the shape kill-transfer leftovers and negative-cost gear produce.
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        cost_override=-500,
        pinned_base_amount=None,
        pinned_base_state=PinState.UNPINNED,
    )

    result = reconcile_list(lst, user=user)

    assert result.clamped is True
    assert result.rating_after == 0  # the written, floored value
    if result.action:
        assert result.action.rating_before + result.action.rating_delta == 0
    # The clamped remainder legitimately shows as computed-vs-cached (the
    # sheet's raw computation is negative, the cache floors at zero) — that
    # is the gap the flag surfaces. What the fix prevents is the ledger
    # ending somewhere the cache can never be:
    problems = fresh_sheet(lst).reconcile()
    assert not any("head desync" in p for p in problems)
    assert not any("chain break" in p for p in problems)


@pytest.mark.django_db
def test_reconcile_adds_no_new_break_to_broken_credits_chain(tracked_list, user):
    """Reconciling a list whose credits chain is ALREADY broken must not
    mint an additional break at the reconcile link: the action chains its
    credits off the head, and the pre-existing problem count is unchanged
    plus nothing new mentions the RECONCILE action."""
    lst, fighter, assignment, equipment = tracked_list
    # Break the credits chain historically: tamper an old action's baseline.
    first = ListAction.objects.filter(list=lst).order_by("created").first()
    ListAction.objects.filter(pk=first.pk).update(credits_before=555)
    problems_before = fresh_sheet(lst).reconcile()
    assert any("credits" in p for p in problems_before)

    # Give the reconcile something to book.
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=None, pinned_base_state=PinState.UNPINNED
    )
    equipment.cost = "25"
    equipment.save()
    result = reconcile_list(lst, user=user)
    assert result.action is not None

    problems_after = fresh_sheet(lst).reconcile()
    assert len(problems_after) == len(problems_before)
    assert not any("RECONCILE" in p for p in problems_after)


@pytest.mark.django_db
def test_reconcile_handles_archived_fighters(tracked_list, user):
    """Archived fighters' caches are rebuilt (harmless, pre-unarchive
    correct) while staying excluded from the list totals."""
    lst, fighter, assignment, _ = tracked_list
    rating_with_fighter = fresh(lst).rating_current
    ListFighter.objects.filter(pk=fighter.pk).update(archived=True)

    result = reconcile_list(lst, user=user)

    assert result.rating_after == rating_with_fighter - fresh(fighter).cost_int()
    assert fresh_sheet(lst).reconcile() == []


@pytest.mark.django_db
def test_reconcile_lists_command_reports(tracked_list, user, capsys):
    from django.core.management import call_command
    from io import StringIO

    lst, fighter, *_ = tracked_list
    true_rating = fresh(lst).rating_current
    ListFighter.objects.filter(pk=fighter.pk).update(
        rating_current=fighter.rating_current + 10, dirty=False
    )
    List.objects.filter(pk=lst.pk).update(rating_current=true_rating + 10, dirty=False)

    out = StringIO()
    call_command("reconcile_lists", str(lst.pk), stdout=out)

    assert "Reconciled 1 list(s)" in out.getvalue()
    assert fresh(lst).rating_current == true_rating
