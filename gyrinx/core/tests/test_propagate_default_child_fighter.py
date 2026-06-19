"""Tests for issue #1725 — propagate pack default child-fighter assignments
to existing gangs.

When a pack author adds a ``ContentFighterDefaultAssignment`` whose equipment
spawns a child fighter (a vehicle / exotic beast via
``ContentEquipmentFighterProfile``), the child fighter should materialise on
*every* already-subscribed gang that has a list-fighter of the relevant type —
not just gangs created after the change.

Cost note: materialising a default child-spawning assignment produces a net
rating delta of ZERO (the default assignment is virtual/0-cost, the direct
assignment uses ``cost_override=0``, and child fighters don't contribute to
list cost). The paired list-action log entry therefore exists for *awareness*
(a new fighter appeared because the pack author changed content), not to
reconcile a cost change — it records the true zero delta and charges no
credits.
"""

from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType

from gyrinx.content.models.default_assignment import ContentFighterDefaultAssignment
from gyrinx.content.models.equipment import (
    ContentEquipmentFighterProfile,
)
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment
from gyrinx.core.models.pack import CustomContentPackItem
from gyrinx.core.tasks import propagate_default_child_fighter_assignment

# Full legacy statline so facts_from_db() can compute on the fly.
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


def _register_pack_item(pack, obj):
    """Register a content object as a pack item (subscriber-visible)."""
    ct = ContentType.objects.get_for_model(type(obj))
    return CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=obj.pk,
        owner=pack.owner,
    )


@pytest.fixture
def child_spawning_setup(pack, content_house, make_content_fighter, make_equipment):
    """Build the common scenario:

    - ``parent_cf``: a GANGER fighter type, registered as pack content
    - ``child_cf``: an EXOTIC_BEAST fighter type (the spawned child)
    - ``equipment``: ContentEquipment with a ContentEquipmentFighterProfile ->
      child_cf, also registered as pack content

    Returns a dict; the default assignment is NOT created yet (each test
    decides when/whether to create it).
    """
    from gyrinx.content.models.fighter import FighterCategoryChoices

    parent_cf = make_content_fighter(
        type="Goliath Driver",
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

    _register_pack_item(pack, parent_cf)
    _register_pack_item(pack, equipment)

    return {
        "pack": pack,
        "parent_cf": parent_cf,
        "child_cf": child_cf,
        "equipment": equipment,
    }


def _subscribed_list_with_parent(make_list, content_house, pack, parent_cf, user):
    """A list subscribed to ``pack`` with one hired list-fighter of parent type.

    The list's cached rating is refreshed after the parent is added so it
    reflects reality (as it would after a normal hire flow). This isolates the
    later materialisation effect in the action-log assertions.
    """
    lst = make_list("Subscribed Gang", content_house=content_house)
    lst.packs.add(pack)
    parent = ListFighter.objects.create(
        list=lst, content_fighter=parent_cf, name="My Driver", owner=user
    )
    lst.facts_from_db(update=True)
    return lst, parent


def _create_default(capture, fighter, equipment):
    """Create a child-spawning default and run the deferred propagation.

    The post_save signal defers the task enqueue to ``transaction.on_commit``;
    pytest's wrapping transaction never commits, so we use
    ``django_capture_on_commit_callbacks(execute=True)`` to fire it (the
    ImmediateBackend then runs the task synchronously).
    """
    with capture(execute=True):
        return ContentFighterDefaultAssignment.objects.create(
            fighter=fighter, equipment=equipment
        )


# --- Signal gating -------------------------------------------------------------


@pytest.mark.django_db
def test_signal_enqueues_only_for_child_spawning_created_default(
    child_spawning_setup, make_equipment, django_capture_on_commit_callbacks
):
    """The post_save signal enqueues the task only when a default is *created*
    AND its equipment has a ContentEquipmentFighterProfile."""
    parent_cf = child_spawning_setup["parent_cf"]
    equipment = child_spawning_setup["equipment"]

    # A plain (non-child-spawning) equipment.
    plain_equipment = make_equipment("Bolt Pistol", category="Pistols", cost="10")

    with patch(
        "gyrinx.core.models.list.signal_handlers.propagate_default_child_fighter_assignment"
    ) as mock_task:
        # Non-child-spawning default -> must NOT enqueue.
        with django_capture_on_commit_callbacks(execute=True):
            ContentFighterDefaultAssignment.objects.create(
                fighter=parent_cf, equipment=plain_equipment
            )
        mock_task.enqueue.assert_not_called()

        # Child-spawning default -> must enqueue exactly once (after commit).
        with django_capture_on_commit_callbacks(execute=True):
            default = ContentFighterDefaultAssignment.objects.create(
                fighter=parent_cf, equipment=equipment
            )
        mock_task.enqueue.assert_called_once_with(default_assignment_id=str(default.pk))

        # Editing the child-spawning default (created=False) -> must NOT re-enqueue.
        mock_task.enqueue.reset_mock()
        with django_capture_on_commit_callbacks(execute=True):
            default.cost = 5
            default.save()
        mock_task.enqueue.assert_not_called()


# --- Core propagation ----------------------------------------------------------


@pytest.mark.django_db
def test_propagation_reaches_existing_subscribed_gang(
    child_spawning_setup,
    make_list,
    content_house,
    user,
    django_capture_on_commit_callbacks,
):
    """Creating a child-spawning default materialises the child fighter on an
    existing subscribed gang's matching list-fighter."""
    parent_cf = child_spawning_setup["parent_cf"]
    child_cf = child_spawning_setup["child_cf"]
    equipment = child_spawning_setup["equipment"]
    pack = child_spawning_setup["pack"]

    lst, parent = _subscribed_list_with_parent(
        make_list, content_house, pack, parent_cf, user
    )

    # Sanity: no child yet.
    assert not ListFighter.objects.filter(list=lst, content_fighter=child_cf).exists()

    _create_default(django_capture_on_commit_callbacks, parent_cf, equipment)

    # Child fighter materialised on the existing parent.
    assert ListFighter.objects.filter(list=lst, content_fighter=child_cf).exists()
    # And a from_default_assignment direct assignment exists on the parent.
    assert ListFighterEquipmentAssignment.objects.filter(
        list_fighter=parent,
        content_equipment=equipment,
        from_default_assignment__isnull=False,
    ).exists()


@pytest.mark.django_db
def test_idempotent_rerun(
    child_spawning_setup,
    make_list,
    content_house,
    user,
    django_capture_on_commit_callbacks,
):
    """Re-running the task does not create duplicate child fighters/assignments."""
    parent_cf = child_spawning_setup["parent_cf"]
    child_cf = child_spawning_setup["child_cf"]
    equipment = child_spawning_setup["equipment"]
    pack = child_spawning_setup["pack"]

    lst, parent = _subscribed_list_with_parent(
        make_list, content_house, pack, parent_cf, user
    )
    default = _create_default(django_capture_on_commit_callbacks, parent_cf, equipment)

    children_before = ListFighter.objects.filter(
        list=lst, content_fighter=child_cf
    ).count()
    assignments_before = ListFighterEquipmentAssignment.objects.filter(
        list_fighter=parent, content_equipment=equipment
    ).count()
    assert children_before == 1

    # Run the task again (enqueue runs synchronously under ImmediateBackend).
    propagate_default_child_fighter_assignment.enqueue(
        default_assignment_id=str(default.pk)
    )

    assert (
        ListFighter.objects.filter(list=lst, content_fighter=child_cf).count()
        == children_before
    )
    assert (
        ListFighterEquipmentAssignment.objects.filter(
            list_fighter=parent, content_equipment=equipment
        ).count()
        == assignments_before
    )


@pytest.mark.django_db
def test_existing_materialised_assignment_untouched(
    child_spawning_setup, make_list, content_house, user
):
    """If a list-fighter already has the materialised assignment, propagation
    leaves it alone (no duplicate, no second action)."""
    parent_cf = child_spawning_setup["parent_cf"]
    child_cf = child_spawning_setup["child_cf"]
    equipment = child_spawning_setup["equipment"]
    pack = child_spawning_setup["pack"]

    lst, parent = _subscribed_list_with_parent(
        make_list, content_house, pack, parent_cf, user
    )
    # Create the default WITHOUT propagation firing, then materialise once.
    with patch(
        "gyrinx.core.models.list.signal_handlers.propagate_default_child_fighter_assignment"
    ):
        default = ContentFighterDefaultAssignment.objects.create(
            fighter=parent_cf, equipment=equipment
        )
    # Materialise manually (simulate already-spawned).
    propagate_default_child_fighter_assignment.enqueue(
        default_assignment_id=str(default.pk)
    )
    assert ListFighter.objects.filter(list=lst, content_fighter=child_cf).count() == 1

    actions_before = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()

    # Run again — nothing new should be created.
    propagate_default_child_fighter_assignment.enqueue(
        default_assignment_id=str(default.pk)
    )
    assert ListFighter.objects.filter(list=lst, content_fighter=child_cf).count() == 1
    assert (
        ListAction.objects.filter(
            list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
        ).count()
        == actions_before
    )


@pytest.mark.django_db
def test_unsubscribed_gang_unaffected(
    child_spawning_setup,
    make_list,
    content_house,
    user,
    django_capture_on_commit_callbacks,
):
    """A list NOT subscribed to the pack does not receive the child fighter."""
    parent_cf = child_spawning_setup["parent_cf"]
    child_cf = child_spawning_setup["child_cf"]
    equipment = child_spawning_setup["equipment"]

    lst = make_list("Unsubscribed Gang", content_house=content_house)
    # NOT subscribed to the pack.
    ListFighter.objects.create(
        list=lst, content_fighter=parent_cf, name="Lone Driver", owner=user
    )

    _create_default(django_capture_on_commit_callbacks, parent_cf, equipment)

    assert not ListFighter.objects.filter(list=lst, content_fighter=child_cf).exists()


@pytest.mark.django_db
def test_archived_pack_item_still_propagates_to_subscriber(
    child_spawning_setup,
    make_list,
    content_house,
    user,
    django_capture_on_commit_callbacks,
):
    """Archive semantics: an archived pack item still propagates to gangs that
    are already subscribed (archived content stays visible to subscribers)."""
    parent_cf = child_spawning_setup["parent_cf"]
    child_cf = child_spawning_setup["child_cf"]
    equipment = child_spawning_setup["equipment"]
    pack = child_spawning_setup["pack"]

    lst, parent = _subscribed_list_with_parent(
        make_list, content_house, pack, parent_cf, user
    )

    # Archive the parent fighter's pack item.
    ct = ContentType.objects.get_for_model(ContentFighter)
    item = CustomContentPackItem.objects.get(
        pack=pack, content_type=ct, object_id=parent_cf.pk
    )
    item.archived = True
    item.save()

    _create_default(django_capture_on_commit_callbacks, parent_cf, equipment)

    assert ListFighter.objects.filter(list=lst, content_fighter=child_cf).exists()


# --- Action log ----------------------------------------------------------------


@pytest.mark.django_db
def test_action_log_entry_created(
    child_spawning_setup,
    make_list,
    content_house,
    user,
    django_capture_on_commit_callbacks,
):
    """An awareness action is logged per affected list, referencing the
    equipment, with a true (zero) rating delta and no credit charge."""
    parent_cf = child_spawning_setup["parent_cf"]
    equipment = child_spawning_setup["equipment"]
    pack = child_spawning_setup["pack"]

    lst, parent = _subscribed_list_with_parent(
        make_list, content_house, pack, parent_cf, user
    )

    before = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).count()

    _create_default(django_capture_on_commit_callbacks, parent_cf, equipment)

    actions = ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    )
    assert actions.count() == before + 1
    action = actions.latest("created")
    assert equipment.name in action.description
    assert action.rating_delta == 0
    assert action.credits_delta == 0


@pytest.mark.django_db
def test_campaign_mode_no_credit_charge(
    child_spawning_setup,
    make_list,
    content_house,
    user,
    django_capture_on_commit_callbacks,
):
    """In campaign mode, propagation must not charge or refund credits."""
    from gyrinx.core.models.list import List

    parent_cf = child_spawning_setup["parent_cf"]
    child_cf = child_spawning_setup["child_cf"]
    equipment = child_spawning_setup["equipment"]
    pack = child_spawning_setup["pack"]

    lst = make_list(
        "Campaign Gang", content_house=content_house, status=List.CAMPAIGN_MODE
    )
    lst.packs.add(pack)
    lst.credits_current = 100
    lst.save()
    ListFighter.objects.create(
        list=lst, content_fighter=parent_cf, name="Driver", owner=user
    )

    _create_default(django_capture_on_commit_callbacks, parent_cf, equipment)

    lst.refresh_from_db()
    assert lst.credits_current == 100
    # Child still materialised.
    assert ListFighter.objects.filter(list=lst, content_fighter=child_cf).exists()


@pytest.mark.django_db
def test_no_action_when_list_has_no_latest_action(
    child_spawning_setup,
    make_list,
    content_house,
    user,
    django_capture_on_commit_callbacks,
):
    """A subscribed list without an initial action still materialises the child
    but records no CONTENT_COST_CHANGE action."""
    parent_cf = child_spawning_setup["parent_cf"]
    child_cf = child_spawning_setup["child_cf"]
    equipment = child_spawning_setup["equipment"]
    pack = child_spawning_setup["pack"]

    lst = make_list(
        "No Initial Action", content_house=content_house, create_initial_action=False
    )
    lst.packs.add(pack)
    ListFighter.objects.create(
        list=lst, content_fighter=parent_cf, name="Driver", owner=user
    )

    _create_default(django_capture_on_commit_callbacks, parent_cf, equipment)

    # Child still materialised.
    assert ListFighter.objects.filter(list=lst, content_fighter=child_cf).exists()
    # But no action recorded (no latest_action to anchor it).
    assert not ListAction.objects.filter(
        list=lst, action_type=ListActionType.CONTENT_COST_CHANGE
    ).exists()


# Out of scope (not tested here, by design):
# - Deleting a default does NOT retract already-spawned child fighters — they
#   are user-owned data once materialised. We add no deletion-propagation, and
#   the from_default_assignment FK uses on_delete=DO_NOTHING.
# - Adding a ContentEquipmentFighterProfile to equipment that already has a
#   default does NOT trigger propagation — the signal fires on default
#   creation only (see test_signal_enqueues_only_for_child_spawning_created_default,
#   which asserts created=False saves do not re-enqueue).
