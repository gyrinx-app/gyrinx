"""
Tests for fighter lifecycle handlers (kill and resurrect).

These tests directly test the handler functions in gyrinx.core.handlers.fighter,
ensuring that business logic works correctly without involving HTTP machinery.
"""

import pytest

from gyrinx.core.handlers.fighter.kill import handle_fighter_kill
from gyrinx.core.handlers.fighter.resurrect import handle_fighter_resurrect
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.list import ListFighter


# ===== Kill Handler Tests =====


@pytest.mark.django_db
def test_handle_fighter_kill_basic(user, list_with_campaign, content_fighter, settings):
    """Test killing a fighter creates correct actions and reduces rating."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    fighter_cost_before = fighter.cost_int()
    rating_before = lst.rating_current

    result = handle_fighter_kill(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify result
    assert result.fighter == fighter
    assert result.fighter_cost_before == fighter_cost_before
    assert result.equipment_count == 0

    # Verify ListAction created
    assert result.list_action is not None
    assert result.list_action.action_type == ListActionType.UPDATE_FIGHTER
    assert result.list_action.rating_delta == -fighter_cost_before
    assert result.list_action.stash_delta == 0
    assert result.list_action.credits_delta == 0
    assert result.list_action.rating_before == rating_before

    # Verify fighter updated
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD
    assert fighter.cost_override == 0

    # Verify CampaignAction created
    assert result.campaign_action is not None
    assert "was killed" in result.campaign_action.description


@pytest.mark.django_db
def test_handle_fighter_kill_propagates_to_fighter_rating_current(
    user, list_with_campaign, content_fighter, settings
):
    """Test that killing a fighter propagates negative delta to fighter.rating_current."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Set initial rating_current manually
    fighter.rating_current = 100
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current
    fighter_cost_before = fighter.cost_int()

    result = handle_fighter_kill(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify rating_delta is negative
    assert result.list_action.rating_delta == -fighter_cost_before

    # Verify fighter.rating_current propagated (reduced to 0)
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating - fighter_cost_before


@pytest.mark.django_db
def test_handle_fighter_kill_with_equipment(
    user, list_with_campaign, content_fighter, make_equipment, settings
):
    """Test killing a fighter with equipment transfers equipment to stash."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    # Create stash fighter
    from gyrinx.models import FighterCategoryChoices

    # We need the make_content_fighter fixture, but we'll create a simple stash manually
    stash_type = content_fighter.__class__.objects.create(
        house=content_fighter.house,
        type="Stash",
        category=FighterCategoryChoices.CREW,
        base_cost=0,
        is_stash=True,
    )
    stash_fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_type,
        list=lst,
        owner=user,
    )

    # Create fighter with equipment
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    equipment = make_equipment("Test Weapon", cost="50")
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    result = handle_fighter_kill(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify equipment transferred
    assert result.equipment_count == 1

    # Verify equipment is now on stash
    assert stash_fighter.listfighterequipmentassignment_set.count() == 1

    # Verify description mentions equipment transfer
    assert "equipment transferred to stash" in result.description.lower()


# ===== Resurrect Handler Tests =====


@pytest.mark.django_db
def test_handle_fighter_resurrect_basic(
    user, list_with_campaign, content_fighter, settings
):
    """Test resurrecting a dead fighter creates correct actions and restores rating."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    # Create a dead fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
        cost_override=0,  # Dead fighters have cost 0
    )

    # Calculate what the restored cost will be
    restored_cost = fighter._base_cost_before_override()
    rating_before = lst.rating_current

    result = handle_fighter_resurrect(
        user=user,
        fighter=fighter,
    )

    # Verify result
    assert result.fighter == fighter
    assert result.restored_cost == restored_cost

    # Verify ListAction created
    assert result.list_action is not None
    assert result.list_action.action_type == ListActionType.UPDATE_FIGHTER
    assert result.list_action.rating_delta == restored_cost
    assert result.list_action.stash_delta == 0
    assert result.list_action.credits_delta == 0
    assert result.list_action.rating_before == rating_before

    # Verify fighter updated
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.ACTIVE
    assert fighter.cost_override is None
    assert fighter.cost_int() == restored_cost

    # Verify CampaignAction created
    assert result.campaign_action is not None
    assert "resurrection" in result.campaign_action.description.lower()


@pytest.mark.django_db
def test_handle_fighter_resurrect_propagates_to_fighter_rating_current(
    user, list_with_campaign, content_fighter, settings
):
    """Test that resurrecting a fighter propagates positive delta to fighter.rating_current."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.rating_current = 500
    lst.save()

    # Create a dead fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
        cost_override=0,
    )

    # Dead fighter starts with rating_current = 0
    fighter.rating_current = 0
    fighter.save()
    fighter.refresh_from_db()
    initial_fighter_rating = fighter.rating_current
    restored_cost = fighter._base_cost_before_override()

    result = handle_fighter_resurrect(
        user=user,
        fighter=fighter,
    )

    # Verify rating_delta is positive
    assert result.list_action.rating_delta == restored_cost

    # Verify fighter.rating_current propagated (increased from 0 to restored_cost)
    fighter.refresh_from_db()
    assert fighter.rating_current == initial_fighter_rating + restored_cost


@pytest.mark.django_db
def test_handle_fighter_resurrect_validates_campaign_mode(
    user, make_list, content_fighter
):
    """Test resurrection only works in campaign mode."""
    lst = make_list("Test List")  # List building mode

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
        cost_override=0,
    )

    with pytest.raises(ValueError, match="campaign mode"):
        handle_fighter_resurrect(
            user=user,
            fighter=fighter,
        )


@pytest.mark.django_db
def test_handle_fighter_resurrect_validates_dead_state(
    user, list_with_campaign, content_fighter
):
    """Test resurrection only works on dead fighters."""
    lst = list_with_campaign

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.ACTIVE,  # Not dead
    )

    with pytest.raises(ValueError, match="dead fighters"):
        handle_fighter_resurrect(
            user=user,
            fighter=fighter,
        )


@pytest.mark.django_db
def test_handle_fighter_resurrect_validates_not_stash(
    user, list_with_campaign, make_content_fighter, content_house
):
    """Test resurrection rejects stash fighters."""
    lst = list_with_campaign

    from gyrinx.models import FighterCategoryChoices

    stash_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )

    stash_fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_type,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
        cost_override=0,
    )

    with pytest.raises(ValueError, match="stash"):
        handle_fighter_resurrect(
            user=user,
            fighter=stash_fighter,
        )


# ===== Stash accounting after kill (regression for stash_current 500) =====
#
# Bug: when a fighter is killed, handle_fighter_kill transfers their equipment
# to the stash and bumps list.stash_current by the equipment cost, but it
# never updates stash_fighter.rating_current. The stash fighter's cached rating
# stays at 0 (or whatever it was). Later reassignment-out from the stash
# decrements stash.rating_current normally, pushing it negative. The next
# refresh_list_cost call writes that negative aggregate to
# list.stash_current (PositiveIntegerField) and a CheckViolation 500s the
# page.


def _make_stash_fighter(*, user, lst, content_fighter):
    """Create a stash fighter on ``lst`` reusing the existing ContentFighter house."""
    from gyrinx.models import FighterCategoryChoices

    stash_type = content_fighter.__class__.objects.create(
        house=content_fighter.house,
        type="Stash",
        category=FighterCategoryChoices.CREW,
        base_cost=0,
        is_stash=True,
    )
    return ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_type,
        list=lst,
        owner=user,
    )


def _make_fighter_with_equipment(*, user, lst, content_fighter, make_equipment, cost):
    """Create a fighter on ``lst`` with one piece of equipment at ``cost`` credits."""
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Test Weapon", cost=str(cost))
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    return fighter, equipment, assignment


@pytest.mark.django_db
def test_handle_fighter_kill_bumps_stash_rating_current(
    user, list_with_campaign, content_fighter, make_equipment, settings
):
    """Kill must bump stash_fighter.rating_current by the transferred equipment cost.

    Without this, list.stash_current (incremented by stash_delta) and
    stash_fighter.rating_current (untouched) drift, and any later reassignment
    out of the stash drives the fighter's cached rating negative.
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign

    stash_fighter = _make_stash_fighter(
        user=user, lst=lst, content_fighter=content_fighter
    )
    stash_initial = stash_fighter.rating_current

    fighter, _eq, _a = _make_fighter_with_equipment(
        user=user,
        lst=lst,
        content_fighter=content_fighter,
        make_equipment=make_equipment,
        cost=50,
    )

    result = handle_fighter_kill(user=user, lst=lst, fighter=fighter)

    assert result.equipment_count == 1
    # list.stash_current bumped by equipment cost (50)
    assert result.list_action.stash_delta == 50

    # Stash fighter cache must move in lock-step with list.stash_current
    stash_fighter.refresh_from_db()
    assert stash_fighter.rating_current == stash_initial + 50


@pytest.mark.django_db
def test_handle_fighter_kill_then_refresh_keeps_list_stash_consistent(
    user, list_with_campaign, content_fighter, make_equipment, settings
):
    """After kill + facts_from_db, list.stash_current must match the kill's stash bump.

    Previously, refresh recomputed stash from stash_fighter.facts() which
    returned the stale rating_current (still 0), so the +equipment bump from
    the kill action got silently undone on the next refresh.
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign

    _make_stash_fighter(user=user, lst=lst, content_fighter=content_fighter)
    fighter, _eq, _a = _make_fighter_with_equipment(
        user=user,
        lst=lst,
        content_fighter=content_fighter,
        make_equipment=make_equipment,
        cost=50,
    )

    handle_fighter_kill(user=user, lst=lst, fighter=fighter)
    lst.refresh_from_db()
    stash_after_kill = lst.stash_current

    # Force the same path that the Refresh Cost button takes.
    lst.facts_from_db(update=True)

    lst.refresh_from_db()
    assert lst.stash_current == stash_after_kill, (
        f"Refresh changed stash_current from {stash_after_kill} to {lst.stash_current}"
    )
    assert lst.stash_current >= 50


@pytest.mark.django_db
def test_transfer_from_stash_after_kill_keeps_counters_non_negative(
    user, list_with_campaign, content_fighter, make_equipment, settings
):
    """Reassigning equipment out of the stash after a kill must not drive either
    stash_fighter.rating_current or list.stash_current below zero.

    This is the precise drift that produced the production CheckViolation.
    """
    from gyrinx.core.handlers.equipment.reassignment import (
        handle_equipment_reassignment,
    )

    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign

    stash_fighter = _make_stash_fighter(
        user=user, lst=lst, content_fighter=content_fighter
    )
    fighter, _eq, _a = _make_fighter_with_equipment(
        user=user,
        lst=lst,
        content_fighter=content_fighter,
        make_equipment=make_equipment,
        cost=50,
    )
    # A second live fighter to receive the stash item.
    receiver = ListFighter.objects.create(
        name="Receiver",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    handle_fighter_kill(user=user, lst=lst, fighter=fighter)

    stash_fighter.refresh_from_db()
    transferred = stash_fighter.listfighterequipmentassignment_set.first()
    assert transferred is not None

    handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=stash_fighter,
        to_fighter=receiver,
        assignment=transferred,
    )

    stash_fighter.refresh_from_db()
    lst.refresh_from_db()
    assert stash_fighter.rating_current >= 0, (
        f"stash rating drifted negative: {stash_fighter.rating_current}"
    )
    assert lst.stash_current >= 0


@pytest.mark.django_db
def test_facts_from_db_clamps_negative_stash_to_zero(
    user, list_with_campaign, content_fighter, settings
):
    """A directly-corrupted negative stash cache must not 500 the refresh path.

    Defense in depth: even if some future code path leaves stash_fighter
    .rating_current negative, facts_from_db must clamp the aggregate to
    satisfy list.stash_current's PositiveIntegerField constraint.
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign

    stash_fighter = _make_stash_fighter(
        user=user, lst=lst, content_fighter=content_fighter
    )
    # Bypass propagation to simulate drift that already exists in production
    # data (e.g. The Ferrous Phalanx, list 478a91b9...).
    ListFighter.objects.filter(pk=stash_fighter.pk).update(
        rating_current=-270, dirty=False
    )

    # Must not raise IntegrityError (CheckViolation on PositiveIntegerField).
    lst.facts_from_db(update=True)

    lst.refresh_from_db()
    assert lst.stash_current == 0, (
        f"Negative stash should clamp to 0, got {lst.stash_current}"
    )


@pytest.mark.django_db
def test_refresh_after_kill_and_transfer_does_not_500(
    user, list_with_campaign, content_fighter, make_equipment, settings
):
    """End-to-end repro of the production 500 on list 478a91b9-...:

    1. Kill a fighter with equipment (equipment moves to stash).
    2. Refresh cost (facts_from_db with update=True).
    3. Reassign the stash item back onto a live fighter.
    4. Refresh cost again — this is the request that produced the
       CheckViolation in production.

    The original code raised django.db.utils.IntegrityError on step 4.
    """
    from gyrinx.core.handlers.equipment.reassignment import (
        handle_equipment_reassignment,
    )

    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign

    stash_fighter = _make_stash_fighter(
        user=user, lst=lst, content_fighter=content_fighter
    )
    fighter, _eq, _a = _make_fighter_with_equipment(
        user=user,
        lst=lst,
        content_fighter=content_fighter,
        make_equipment=make_equipment,
        cost=50,
    )
    receiver = ListFighter.objects.create(
        name="Receiver",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    handle_fighter_kill(user=user, lst=lst, fighter=fighter)
    lst.facts_from_db(update=True)  # the user's first Refresh

    stash_fighter.refresh_from_db()
    transferred = stash_fighter.listfighterequipmentassignment_set.first()
    assert transferred is not None
    handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=stash_fighter,
        to_fighter=receiver,
        assignment=transferred,
    )

    # This is the call that raised in production.
    lst.facts_from_db(update=True)

    lst.refresh_from_db()
    assert lst.stash_current >= 0
    assert lst.rating_current >= 0
