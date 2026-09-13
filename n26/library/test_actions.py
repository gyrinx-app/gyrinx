from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from n26.core.access import actions_for, rank_tables_for
from n26.core.render import build_model_card
from n26.library import authoring
from n26.library.models import (
    Action,
    ActionPriceComponent,
    AddsAssignable,
    Counter,
    Pickable,
    Picklist,
    RankTable,
    Slot,
    SlotType,
)
from n26.tests.sandbox.actions import (
    adds,
    assign,
    create_default_set,
    create_wargear,
    found_gang,
    hire_with_option,
    modifier,
    removes,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def fighter(gang_type, make_profile):
    player = User.objects.create_user("action-player")
    gang = found_gang("The Long Hunt", gang_type, owner=player, budget=1000)
    return hire_with_option(gang, make_profile("Hunt champion", price=100), "Kora")


def test_actions_and_rank_tables_use_every_assignable_registry():
    xp = Counter.objects.create(name="XP")
    action = Action.objects.create(name="Advancement", timing=Action.Timing.POST_CYCLE)
    table = RankTable.objects.create(name="Standard ranks", counter=xp)

    assert AddsAssignable.objects.create(action=action).thing == action
    assert AddsAssignable.objects.create(rank_table=table).thing == table
    assert authoring.ef_adds(action).thing == action
    assert authoring.ef_removes(table).thing == table

    from n26.core.models import Assignment

    assert Assignment(action=action).assignable == action
    assert Assignment(rank_table=table).assignable == table


def test_action_authoring_keeps_acquisition_and_use_prices_separate():
    glitches = Counter.objects.create(name="Glitch count")
    operation = authoring.apply_changes(authoring.counter_change(glitches, "set", 0))
    outcome = authoring.create_outcome("Clear glitches", operation)

    action = authoring.create_action(
        "Suit maintenance",
        "post_cycle",
        outcomes=[outcome],
        use_price=[{"resource": "credits", "payer": "gang", "amount": 100}],
    )

    assert action.price == 0
    assert [member.outcome for member in action.outcomes.all()] == [outcome]
    assert [(part.resource, part.amount) for part in action.use_price.all()] == [
        ("credits", 100)
    ]


def test_action_names_include_the_author_qualifier_and_may_have_an_acquisition_price():
    Action.objects.create(
        name="Maintenance", qualifier="Hunt master", timing="post_cycle", price=5
    )
    Action.objects.create(
        name="Maintenance", qualifier="Malcadon", timing="post_cycle", price=10
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Action.objects.create(
            name="maintenance", qualifier="hunt master", timing="post_cycle"
        )


def test_price_components_are_positive_and_typed():
    action = Action.objects.create(name="Maintenance", timing="post_cycle")
    with pytest.raises(ValidationError):
        authoring.add_action_price_component(action, "credits", "fighter", 10)
    with pytest.raises(IntegrityError), transaction.atomic():
        ActionPriceComponent.objects.create(
            action=action, resource="credits", payer="gang", amount=0
        )


def test_rank_thresholds_are_positive_unique_and_ordered():
    table = authoring.create_rank_table(
        "Standard ranks", Counter.objects.create(name="XP"), thresholds=[60, 6, 31]
    )
    assert list(table.thresholds.values_list("threshold", flat=True)) == [6, 31, 60]
    with pytest.raises(IntegrityError), transaction.atomic():
        authoring.add_rank_threshold(table, 31)


def test_a_tier_ladder_requires_one_pick_and_numeric_levels():
    kind = SlotType.objects.create(name="Augmentation")
    picklist = Picklist.objects.create(name="Augmentations", slot_type=kind)
    Picklist.objects.get(pk=picklist.pk)
    pick = Pickable.objects.create(name="Tier 1", slot_type=kind)
    authoring.add_picklist_member(picklist, pick, level=1)
    slot = Slot(
        name="Augmentation",
        slot_type=kind,
        picklist=picklist,
        mode="tier_ladder",
        max_picks=2,
    )
    with pytest.raises(ValidationError, match="one tier"):
        slot.full_clean()


class _Card:
    def __init__(self, nodes):
        self.nodes = nodes

    def all_nodes(self):
        return self.nodes


def _node(key, assignable, attribute, cause=None, suppressed=False):
    return SimpleNamespace(
        key=key,
        assignable=assignable,
        assignment=SimpleNamespace(**{f"{attribute}_id": assignable.pk}),
        caused_by_key=cause,
        suppressed=suppressed,
        name=str(assignable),
    )


def test_access_readers_deduplicate_stored_and_computed_sources_without_queries(
    django_assert_num_queries,
):
    xp = Counter.objects.create(name="XP")
    action = Action.objects.create(name="Advancement", timing="post_cycle")
    table = RankTable.objects.create(name="Standard ranks", counter=xp)
    source = SimpleNamespace(
        key="source",
        name="Hunt master",
        assignment=None,
        suppressed=False,
        caused_by_key=None,
    )
    action_node = _node("action", action, "action", cause="source")
    table_node = _node("table", table, "rank_table")
    card = _Card([source, action_node, table_node])
    computed = SimpleNamespace(
        acquired=[SimpleNamespace(thing=action, source="duplicate")], echoed=[]
    )

    with django_assert_num_queries(0):
        action_access = actions_for(SimpleNamespace(), card=card, computed=computed)
        table_access = rank_tables_for(SimpleNamespace(), card=card, computed=computed)

    assert [
        (found.action, found.source, found.computed) for found in action_access
    ] == [(action, "Hunt master", False)]
    assert [(found.rank_table, found.computed) for found in table_access] == [
        (table, False)
    ]


def test_real_card_access_honours_direct_computed_and_removed_actions(
    fighter, django_assert_num_queries
):
    action = Action.objects.create(name="Suit evolution", timing="post_cycle")
    direct = assign(action, miniature=fighter)
    charm = create_wargear("Evolution rig")
    modifier("Rig grants evolution", targets_model(), adds(action), carried_by=charm)
    carried = assign(charm, miniature=fighter)

    (access,) = actions_for(fighter)
    assert access.action == action
    assert access.computed is False
    with django_assert_num_queries(0):
        assert access.usability == ""
    card = build_model_card(fighter)
    assert all(line.name != action.name for line in card.equipment)

    direct.archive()
    (access,) = actions_for(fighter)
    assert access.computed is True

    blocker = create_wargear("Damaged controls")
    modifier(
        "Controls stop evolution", targets_model(), removes(action), carried_by=blocker
    )
    assign(blocker, miniature=fighter)
    assert actions_for(fighter) == []

    carried.archive()


def test_a_rank_table_built_into_a_profile_is_effective(gang_type, make_profile):
    xp = Counter.objects.create(name="XP")
    table = RankTable.objects.create(name="Standard ranks", counter=xp)
    profile = make_profile("Ranked hunter", price=100)
    profile.built_ins = create_default_set("Ranks", members=[table])
    profile.save()
    player = User.objects.create_user("rank-player")
    gang = found_gang("Rank hunters", gang_type, owner=player, budget=1000)
    fighter = hire_with_option(gang, profile, "Vex")
    assert [access.rank_table for access in rank_tables_for(fighter)] == [table]


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        ("/n26/authoring/action/", "Actions"),
        ("/n26/authoring/rank-table/", "Rank tables"),
    ],
)
def test_action_foundations_have_authoring_pages(admin_client, path, heading):
    response = admin_client.get(path)
    assert response.status_code == 200
    assert heading in response.content.decode()
