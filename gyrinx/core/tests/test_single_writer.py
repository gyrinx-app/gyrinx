"""The single-writer contract for the list-level cost caches.

Exactly one system writes ``List.rating_current``/``stash_current`` on the
push path — the propagation layer. ``create_action`` records the movement
but never applies it, and campaign credits move only through explicit
application (``spend_credits``/``apply_credit_delta``). These tests pin the
contract three ways: by query count (one UPDATE per mutation), by a full
lifecycle walked against live compute, and by credits applied exactly once.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.core.handlers.equipment.sale import SaleItemDetail, handle_equipment_sale
from gyrinx.core.handlers.fighter.kill import handle_fighter_kill
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.list import List
from gyrinx.core.tests.test_balance_sheet import (
    buy_equipment,
    fresh,
    fresh_sheet,
    hire_fighter,
)


@pytest.fixture(autouse=True)
def _action_system_on(settings):
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True


def stake_credits(user, lst, amount):
    """Grant starting credits with a matching ledger entry."""
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Starting stake",
        credits_delta=amount,
    )
    lst.apply_credit_delta(amount)


@pytest.fixture
def tracked_list(user, make_list, content_fighter):
    """A list-building gang with a bootstrap action and one fighter."""
    lst = make_list("Single Writer Gang", create_initial_action=True)
    fighter = hire_fighter(user, lst, content_fighter, name="Scribe")
    return fresh(lst), fresh(fighter)


@pytest.mark.django_db
def test_exactly_one_update_writes_list_rating_per_purchase(
    user, tracked_list, make_equipment
):
    """A purchase issues exactly one UPDATE against the list's rating cache.

    More than one means two writers are applying the movement (the historic
    double-application class of bug); zero means nobody is and the cache
    silently stales.
    """
    lst, fighter = tracked_list
    equipment = make_equipment("Counting Gun", cost="30")

    with CaptureQueriesContext(connection) as ctx:
        buy_equipment(user, lst, fighter, equipment)

    rating_updates = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith("UPDATE")
        and "core_list" in q["sql"]
        and "core_listfighter" not in q["sql"]
        and "rating_current" in q["sql"]
    ]
    assert len(rating_updates) == 1, rating_updates

    # And the one write applied exactly the recorded movement: the cached
    # rating equals the fighter's live cost (gun included).
    lst = fresh(lst)
    assert lst.rating_current == fresh(fighter).cost_int()
    assert fresh_sheet(lst).reconcile() == []


@pytest.mark.django_db
def test_full_lifecycle_facts_match_live_compute(
    user, make_list, make_campaign, content_fighter, make_equipment
):
    """Cached facts equal live compute at every lifecycle step.

    Walks hire → buy → sell-from-stash → kill through the real handlers,
    asserting on FRESH instances (cached properties never carry over) that
    the persisted caches match a from-scratch recompute, without any
    recompute having run in between.
    """
    lst = make_list(
        "Lifecycle Gang",
        create_initial_action=True,
        status=List.CAMPAIGN_MODE,
        campaign=make_campaign("Lifecycle Campaign"),
    )
    stake_credits(user, lst, 500)
    stash = lst.ensure_stash()

    def assert_books_match():
        clean = List.objects.with_related_data(with_fighters=True).get(pk=lst.pk)
        computed = clean.facts_from_db(update=False)
        assert computed.rating == clean.rating_current
        assert computed.stash == clean.stash_current
        assert fresh_sheet(clean).reconcile() == []

    fighter = hire_fighter(user, fresh(lst), content_fighter, name="Walker")
    assert_books_match()

    buy_equipment(
        user, fresh(lst), fighter, make_equipment("Lifecycle Blade", cost="25")
    )
    assert_books_match()

    handle_fighter_kill(user=user, lst=fresh(lst), fighter=fresh(fighter))
    assert_books_match()

    # The blade moved to the stash on death; sell it from there.
    stash = fresh(stash)
    moved = stash.listfighterequipmentassignment_set.get()
    handle_equipment_sale(
        user=user,
        lst=fresh(lst),
        fighter=stash,
        assignment=moved,
        sale_items=[
            SaleItemDetail(
                name=moved.content_equipment.name,
                cost=moved.cost_int(),
                sale_price=10,
                dice_roll=None,
            )
        ],
        sell_assignment=True,
        profiles_to_remove=[],
        accessories_to_remove=[],
        dice_count=0,
        dice_rolls=[],
    )
    assert_books_match()


@pytest.mark.django_db
def test_campaign_credits_apply_exactly_once_on_sale(
    user, make_list, make_campaign, content_fighter, make_equipment
):
    """Sale proceeds land in credits_current exactly once, and the credits
    ledger stays reconcilable (anchor + Σ deltas == cached)."""
    lst = make_list(
        "Credit Gang",
        create_initial_action=True,
        status=List.CAMPAIGN_MODE,
        campaign=make_campaign("Credit Campaign"),
    )
    stake_credits(user, lst, 200)
    stash = lst.ensure_stash()
    gear = buy_equipment(
        user, fresh(lst), fresh(stash), make_equipment("Stock Rifle", cost="40")
    )

    credits_before = fresh(lst).credits_current
    handle_equipment_sale(
        user=user,
        lst=fresh(lst),
        fighter=fresh(stash),
        assignment=fresh(gear),
        sale_items=[
            SaleItemDetail(name="Stock Rifle", cost=40, sale_price=25, dice_roll=None)
        ],
        sell_assignment=True,
        profiles_to_remove=[],
        accessories_to_remove=[],
        dice_count=0,
        dice_rolls=[],
    )

    lst = fresh(lst)
    assert lst.credits_current == credits_before + 25
    assert fresh_sheet(lst).reconcile() == []
