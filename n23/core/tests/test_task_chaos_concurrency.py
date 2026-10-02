"""Concurrency chaos: two *simultaneous* deliveries of the same task.

An at-least-once queue (Pub/Sub, or the local worker pool with >1 worker) can
deliver the same message to two handlers at the same time. The propagation tasks
guard against duplicates with check-then-act logic (``ListAction.exists()``,
materialisation ``exists()``) that is not backed by a row lock or a unique
constraint — so a *sequential* redelivery is caught, but a *concurrent* one may
not be.

These tests run two deliveries on separate threads against a real (committed)
database, using a ``threading.Barrier`` to force both past the idempotency guard
before either commits — the exact interleaving a concurrent redelivery produces.
Both reproduced a real double-apply (double-charged campaign credits; a duplicate
child fighter); both are now fixed by taking a ``select_for_update`` lock on the
``List`` row for the per-list transaction, which serialises concurrent deliveries
so the existing check-then-act guards see the first delivery's committed effect
and skip. These tests now pass and guard against a regression of that fix.
"""

import threading
from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection

from n23.core.models.action import ListAction, ListActionType
from n23.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    _materialise_child_fighter_defaults,
)
from n23.core.tasks import (
    propagate_content_cost_change,
    propagate_default_child_fighter_assignment,
)

pytestmark = pytest.mark.core


def _run_concurrently(target, *, n=2, timeout=15):
    """Run ``target`` on ``n`` threads concurrently.

    Each caller synchronises the threads itself by patching a method with a
    ``threading.Barrier`` wait, so that all ``n`` are inside the critical section
    (past the idempotency guard) simultaneously. Fails the test if a thread
    deadlocks (still alive after the join timeout) or raises — otherwise those
    would surface only as confusing partial-state assertion failures. Returns the
    (empty) list of thread exceptions.
    """
    errors = []

    def wrapped():
        try:
            target()
        except Exception as e:  # noqa: BLE001 - surface, don't swallow
            errors.append(e)
        finally:
            connection.close()

    threads = [threading.Thread(target=wrapped) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)

    stuck = [t for t in threads if t.is_alive()]
    assert not stuck, (
        f"{len(stuck)} delivery thread(s) did not finish within {timeout}s (deadlock?)"
    )
    assert not errors, f"delivery thread(s) raised: {errors!r}"
    return errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("worker", ["reconcile", "pinned_cost", "refresh"])
def test_cache_worker_racing_death_uses_shared_lock_order(
    user,
    list_with_campaign,
    content_fighter,
    stash_fighter_type,
    make_list_fighter,
    make_equipment,
    worker,
):
    import time

    from n23.content.models.signal_handlers import _create_content_cost_change_actions
    from n23.core.cost.reconcile import reconcile_list
    from n23.core.handlers.fighter.kill import handle_fighter_kill
    from n23.core.tasks import refresh_list_facts
    from n23.core.tests.test_balance_sheet import (
        assert_reconciles,
        buy_equipment,
        fresh,
        hire_fighter,
    )

    lst = list_with_campaign
    lst.apply_credit_delta(1000)
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        credits_before=0,
        credits_delta=1000,
        description="Starting credits",
    )
    fighter = hire_fighter(user, lst, content_fighter)
    stash = make_list_fighter(lst, "Stash", content_fighter=stash_fighter_type)
    equipment = make_equipment("Race gear", cost=20)
    buy_equipment(user, lst, fighter, equipment)
    credits_before = fresh(lst).credits_current
    if worker == "pinned_cost":
        type(equipment).objects.filter(pk=equipment.pk).update(cost=25)
        equipment.refresh_from_db()
    expected_stash = 25 if worker == "pinned_cost" else 20
    locked = threading.Event()
    confirmation_attempted = threading.Event()
    confirmation_pid = []
    roles = iter(["worker", "death"])
    deaths = []

    def pause_locked_worker(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not locked.is_set() and "FOR " in sql and f'"{List._meta.db_table}"' in sql:
            locked.set()
            assert confirmation_attempted.wait(timeout=5)
            with connection.cursor() as cursor:
                for _ in range(100):
                    cursor.execute(
                        "SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))",
                        [confirmation_pid[0]],
                    )
                    if cursor.fetchone()[0]:
                        break
                    time.sleep(0.02)
                else:
                    pytest.fail("Confirmation did not wait for the cache worker")
        return result

    def announce_confirmation(execute, sql, params, many, context):
        if "FOR NO KEY UPDATE" in sql and f'"{ListFighter._meta.db_table}"' in sql:
            confirmation_attempted.set()
        return execute(sql, params, many, context)

    def refresh_or_confirm():
        if next(roles) == "worker":
            with connection.execute_wrapper(pause_locked_worker):
                if worker == "reconcile":
                    reconcile_list(fresh(lst), user=user)
                elif worker == "pinned_cost":
                    _create_content_cost_change_actions(equipment, old_cost=20)
                else:
                    refresh_list_facts.func(list_id=str(lst.pk))
        else:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                confirmation_pid.append(cursor.fetchone()[0])
            assert locked.wait(timeout=5)
            with connection.execute_wrapper(announce_confirmation):
                deaths.append(
                    handle_fighter_kill(
                        user=user, lst=fresh(lst), fighter=fresh(fighter)
                    )
                )

    _run_concurrently(refresh_or_confirm)

    assert deaths[0].fighter_cost_before == (
        content_fighter.cost_for_house(lst.content_house) + expected_stash
    )
    assert fresh(fighter).injury_state == ListFighter.DEAD
    assert fresh(fighter).rating_current == fresh(lst).rating_current == 0
    assert fresh(lst).stash_current == fresh(stash).rating_current == expected_stash
    assert fresh(lst).credits_current == credits_before - (expected_stash - 20)
    assert stash.listfighterequipmentassignment_set.count() == 1
    assert_reconciles(lst)


# ---------------------------------------------------------------------------
# propagate_content_cost_change — campaign credit double-charge
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_concurrent_redelivery_charges_campaign_credits_once(
    make_list, make_list_fighter, make_equipment
):
    """Two simultaneous deliveries of a cost change must charge campaign credits
    exactly once. The per-list select_for_update lock in
    _create_content_cost_change_actions serialises them, so the second delivery
    hits the ListAction.exists() guard and skips."""
    equipment = make_equipment("Boltgun", cost="100", category="Weapons & Ammo")
    lst = make_list("Campaign Gang", status=List.CAMPAIGN_MODE)
    lst.credits_current = 500
    lst.save()
    fighter = make_list_fighter(lst, "Fighter")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=equipment
    )
    lst.facts_from_db(update=True)
    lst.refresh_from_db()

    credits_before = lst.credits_current
    old_rating, old_stash = lst.rating_current, lst.stash_current

    # Apply the content cost change and mark the list dirty (as the pre_save
    # handler would), then deliver the task twice with the same frozen snapshot.
    type(equipment).objects.filter(pk=equipment.pk).update(cost="150")
    equipment.refresh_from_db()
    equipment.set_dirty()
    snapshot = {str(lst.id): [old_rating, old_stash]}
    ct = ContentType.objects.get_for_model(type(equipment))

    barrier = threading.Barrier(2)
    orig_facts = List.facts_from_db

    def synced_facts(self, *args, **kwargs):
        # Sync the two deliveries here: both have already passed the
        # ListAction.exists() guard (which precedes facts_from_db) by the time
        # they arrive, so releasing the barrier lets both create an action.
        if self.pk == lst.pk:
            try:
                barrier.wait(timeout=2)
            except threading.BrokenBarrierError:
                # Expected once the fix is in place: the select_for_update lock
                # serialises the two deliveries, so the second thread cannot reach
                # the barrier while the first holds the lock, and the wait times
                # out. Swallow it and let this delivery proceed — the assertions
                # below verify the single-charge outcome regardless of ordering.
                pass
        return orig_facts(self, *args, **kwargs)

    def deliver():
        propagate_content_cost_change.func(
            content_type_id=ct.id,
            object_id=str(equipment.pk),
            before_snapshots=snapshot,
        )

    with patch.object(List, "facts_from_db", synced_facts):
        _run_concurrently(deliver)

    lst.refresh_from_db()
    actions = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()

    # Correct behaviour: exactly one action, charged exactly once.
    assert actions == 1, f"duplicate CONTENT_COST_CHANGE actions: {actions}"
    assert lst.credits_current == credits_before - 50, (
        f"credits double-charged: {lst.credits_current} "
        f"(expected {credits_before - 50})"
    )


# ---------------------------------------------------------------------------
# propagate_default_child_fighter_assignment — duplicate child fighter
# ---------------------------------------------------------------------------

_STATS = dict(
    movement='5"',
    weapon_skill="4+",
    ballistic_skill="4+",
    strength="3",
    toughness="3",
    wounds="1",
    initiative="4+",
    attacks="1",
    leadership="7+",
    cool="7+",
    willpower="7+",
    intelligence="7+",
)


@pytest.mark.django_db(transaction=True)
def test_concurrent_redelivery_child_fighter_materialises_once(
    pack, content_house, make_content_fighter, make_equipment, make_list, user
):
    """Two simultaneous deliveries of the child-fighter propagation must spawn
    exactly one child. The per-list select_for_update lock in the task serialises
    them, so the second delivery's materialisation guard sees the first's
    committed assignment and skips."""
    from n23.content.models.default_assignment import (
        ContentFighterDefaultAssignment,
    )
    from n23.content.models.equipment import ContentEquipmentFighterProfile
    from n23.content.models.fighter import FighterCategoryChoices
    from n23.core.models.pack import CustomContentPackItem

    parent_cf = make_content_fighter(
        type="Driver",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=60,
        **_STATS,
    )
    child_cf = make_content_fighter(
        type="Hive Cur",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=content_house,
        base_cost=25,
        **_STATS,
    )
    equipment = make_equipment("Hive Cur", category="Status Items", cost="25")
    ContentEquipmentFighterProfile.objects.create(
        equipment=equipment, content_fighter=child_cf
    )
    for obj in (parent_cf, equipment):
        CustomContentPackItem.objects.create(
            pack=pack,
            content_type=ContentType.objects.get_for_model(type(obj)),
            object_id=obj.pk,
            owner=pack.owner,
        )

    lst = make_list("Subscribed Gang", content_house=content_house)
    lst.packs.add(pack)
    ListFighter.objects.create(
        list=lst, content_fighter=parent_cf, name="Driver", owner=user
    )
    lst.facts_from_db(update=True)

    # Create the default WITHOUT propagation, so both concurrent deliveries start
    # from the un-materialised state.
    with patch(
        "n23.core.models.list.signal_handlers."
        "propagate_default_child_fighter_assignment"
    ):
        default = ContentFighterDefaultAssignment.objects.create(
            fighter=parent_cf, equipment=equipment
        )

    barrier = threading.Barrier(2)

    # The task does `from n23.core.models.list import
    # _materialise_child_fighter_defaults` at call time, so patch the name on the
    # PACKAGE (what the import reads), not on the fighter submodule.
    orig = _materialise_child_fighter_defaults
    sync_hits = []

    def synced(list_fighter):
        sync_hits.append(1)
        try:
            barrier.wait(timeout=2)  # both deliveries pass the guard, then release
        except threading.BrokenBarrierError:
            # Expected once the fix is in place: the select_for_update lock
            # serialises the two deliveries, so they no longer arrive at the
            # barrier together and the wait times out. Swallow it and let this
            # delivery proceed — the assertions below verify a single child is
            # materialised regardless of ordering.
            pass
        return orig(list_fighter)

    def deliver():
        propagate_default_child_fighter_assignment.func(
            default_assignment_id=str(default.pk)
        )

    with patch("n23.core.models.list._materialise_child_fighter_defaults", synced):
        _run_concurrently(deliver)

    # Sanity: both deliveries really did reach the synchronised critical section
    # (so the duplication below is the deterministic interleaving, not a fluke).
    assert len(sync_hits) == 2, f"barrier not reached by both threads: {sync_hits}"

    children = ListFighter.objects.filter(list=lst, content_fighter=child_cf).count()
    assignments = ListFighterEquipmentAssignment.objects.filter(
        list_fighter__list=lst,
        content_equipment=equipment,
        from_default_assignment=default,
    ).count()
    assert children == 1, f"duplicate child fighters materialised: {children}"
    assert assignments == 1, f"duplicate default assignments: {assignments}"
