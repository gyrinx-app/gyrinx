"""Tests for the `migrate_persistent_stash_items` management command (#1825)."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
)
from gyrinx.core.maintenance.persistent_stash import find_candidates
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment


_SCENARIO_SEQ = 0


def _setup_scenario(
    content_house,
    make_content_fighter,
    make_list,
    make_list_fighter,
    *,
    persistent: bool = True,
    dying_state: str = ListFighter.DEAD,
    dying_archived: bool = False,
    create_kill_action: bool = True,
):
    """Build a campaign list with one dead fighter + a persistent-cat item on
    the stash, plus a matching kill ListAction. Returns the relevant objects."""
    global _SCENARIO_SEQ
    _SCENARIO_SEQ += 1
    suffix = f" #{_SCENARIO_SEQ}"
    cat = ContentEquipmentCategory.objects.create(
        name=f"Mutations Test{suffix}",
        group="Gear",
        persistent=persistent,
    )
    cat.restricted_to.add(content_house)
    equipment = ContentEquipment.objects.create(
        name=f"Vast Bulk{suffix}", category=cat, cost=10
    )

    stash_cf = make_content_fighter(
        type="Stash",
        category="STASH",
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    ganger_cf = make_content_fighter(
        type="Test Ganger",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )

    gang_list = make_list("Test Gang", status="campaign_mode")
    stash = make_list_fighter(gang_list, "Stash", content_fighter=stash_cf)
    dying = make_list_fighter(
        gang_list,
        "Bozur",
        content_fighter=ganger_cf,
        injury_state=dying_state,
        archived=dying_archived,
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash, content_equipment=equipment
    )
    kill_action = None
    if create_kill_action:
        kill_action = ListAction.objects.create(
            list=gang_list,
            owner=gang_list.owner,
            applied=True,
            action_type=ListActionType.UPDATE_FIGHTER,
            description=f"{dying.name} was killed (50¢). All equipment transferred to stash.",
            list_fighter=dying,
            rating_delta=-50,
            stash_delta=10,
            credits_delta=0,
            rating_before=50,
            stash_before=0,
            credits_before=0,
        )
    return {
        "list": gang_list,
        "stash": stash,
        "dying": dying,
        "assignment": assignment,
        "kill_action": kill_action,
    }


def _run(apply: bool = False):
    out = StringIO()
    call_command(
        "migrate_persistent_stash_items",
        apply=apply,
        verbose_skips=True,
        stdout=out,
    )
    return out.getvalue()


# ---------------------------------------------------------------- happy path


@pytest.mark.django_db
def test_apply_moves_persistent_stash_item_to_dead_fighter(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    out = _run(apply=True)

    s["assignment"].refresh_from_db()
    assert s["assignment"].list_fighter_id == s["dying"].id, (
        "assignment should now be on the dying fighter"
    )
    assert "MOVE" in out and "Vast Bulk" in out and "Bozur" in out


@pytest.mark.django_db
def test_apply_appends_audit_list_action(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    _run(apply=True)

    audits = ListAction.objects.filter(
        list=s["list"], description__icontains="data repair"
    )
    assert audits.count() == 1
    audit = audits.get()
    assert "Vast Bulk" in audit.description
    assert "Bozur" in audit.description
    assert audit.applied is True


@pytest.mark.django_db
def test_apply_recomputes_list_stash_cost(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    # Mimic the kill handler's propagation: it bumped both the stash fighter's
    # cached rating AND the list's stash_current by the dying-fighter cost,
    # without marking either dirty. The command must force them to reconcile
    # against actual assignments (= 0 after the move), not return the stale
    # bumped values.
    s["stash"].rating_current = 25
    s["stash"].dirty = False
    s["stash"].save(update_fields=["rating_current", "dirty"])
    s["list"].stash_current = 25
    s["list"].dirty = False
    s["list"].save(update_fields=["stash_current", "dirty"])

    _run(apply=True)

    s["list"].refresh_from_db()
    s["stash"].refresh_from_db()
    # After move, stash has 0 assignments → both caches recompute to 0.
    assert s["list"].stash_current == 0
    assert s["list"].dirty is False
    assert s["stash"].rating_current == 0


# ---------------------------------------------------------------- dry-run


@pytest.mark.django_db
def test_dry_run_does_not_move(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    out = _run(apply=False)

    s["assignment"].refresh_from_db()
    assert s["assignment"].list_fighter_id == s["stash"].id, (
        "dry-run must not modify the assignment"
    )
    assert "WOULD MOVE" in out
    assert not ListAction.objects.filter(description__icontains="data repair").exists()


# ---------------------------------------------------------------- skip paths


@pytest.mark.django_db
def test_skip_no_kill_action(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house,
        make_content_fighter,
        make_list,
        make_list_fighter,
        create_kill_action=False,
    )
    out = _run(apply=True)

    s["assignment"].refresh_from_db()
    assert s["assignment"].list_fighter_id == s["stash"].id
    assert "no_match" in out


@pytest.mark.django_db
def test_skip_when_fighter_alive(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house,
        make_content_fighter,
        make_list,
        make_list_fighter,
        dying_state=ListFighter.ACTIVE,
    )
    out = _run(apply=True)

    s["assignment"].refresh_from_db()
    assert s["assignment"].list_fighter_id == s["stash"].id
    assert "alive" in out


@pytest.mark.django_db
def test_skip_when_fighter_archived(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house,
        make_content_fighter,
        make_list,
        make_list_fighter,
        dying_archived=True,
    )
    out = _run(apply=True)

    s["assignment"].refresh_from_db()
    assert s["assignment"].list_fighter_id == s["stash"].id
    assert "archived" in out


@pytest.mark.django_db
def test_skip_ambiguous_when_multiple_kill_actions_within_window(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    # Second dying fighter + kill action in the same instant
    other_cf = make_content_fighter(
        type="Other Ganger",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    other = make_list_fighter(
        s["list"],
        "Other",
        content_fighter=other_cf,
        injury_state=ListFighter.DEAD,
    )
    ListAction.objects.create(
        list=s["list"],
        owner=s["list"].owner,
        applied=True,
        action_type=ListActionType.UPDATE_FIGHTER,
        description="Other was killed (50¢). All equipment transferred to stash.",
        list_fighter=other,
    )

    out = _run(apply=True)

    s["assignment"].refresh_from_db()
    assert s["assignment"].list_fighter_id == s["stash"].id
    assert "ambiguous" in out


@pytest.mark.django_db
def test_skip_when_matched_action_has_null_list_fighter(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    # Detach the dying fighter from the action (simulates hard-deleted fighter)
    s["kill_action"].list_fighter = None
    s["kill_action"].save()

    out = _run(apply=True)

    s["assignment"].refresh_from_db()
    assert s["assignment"].list_fighter_id == s["stash"].id
    assert "null_fighter" in out


# ---------------------------------------------------------------- perf


@pytest.mark.django_db
def test_find_candidates_is_not_n_plus_1(
    db, content_house, make_content_fighter, make_list, make_list_fighter
):
    """find_candidates must batch the kill-action lookup, not run one query
    per candidate assignment. Locks in the fix for the dry-run page perf."""
    # Build 8 independent scenarios → 8 candidate assignments to classify.
    for _ in range(8):
        _setup_scenario(
            content_house, make_content_fighter, make_list, make_list_fighter
        )

    with CaptureQueriesContext(connection) as ctx:
        candidates = find_candidates()
    assert len(candidates) == 8

    # Hard ceiling: well below 1-per-candidate. The actual count is small
    # (a handful of SELECTs for the assignment query, prefetched joins, and
    # a single batched kill-action query) but pinning the exact number is
    # brittle — anything that grows with N is what we care about.
    assert len(ctx.captured_queries) < 20, (
        f"find_candidates issued {len(ctx.captured_queries)} queries for "
        f"8 assignments — suspect N+1 regression. "
        f"Queries: {[q['sql'][:80] for q in ctx.captured_queries]}"
    )
