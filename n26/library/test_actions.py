from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from n26.core.access import actions_for, rank_table_for, rank_tables_for
from n26.core.operations import Refusal
from n26.core.render import build_model_card
from n26.library import authoring
from n26.library.forms import generate_form
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
from n26.library.specs import specs
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


def test_action_authoring_rejects_an_allowance_and_price_without_partial_rows():
    rule = authoring.recruitment_allowance_rule()
    before = (Action.objects.count(), ActionPriceComponent.objects.count())
    with pytest.raises(ValidationError, match="allowance rule"):
        authoring.create_action(
            "Recruitment augmentation",
            "recruitment",
            allowance_rule=rule,
            use_price=[{"resource": "credits", "payer": "gang", "amount": 10}],
        )
    assert (Action.objects.count(), ActionPriceComponent.objects.count()) == before


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


def test_a_tier_ladder_rejects_an_unlevelled_member_added_or_edited_later():
    kind = SlotType.objects.create(name="Augmentation")
    picklist = Picklist.objects.create(name="Augmentations", slot_type=kind)
    first = Pickable.objects.create(name="Tier 1", slot_type=kind)
    member = authoring.add_picklist_member(picklist, first, level=1)
    Slot.objects.create(
        name="Augmentation",
        slot_type=kind,
        picklist=picklist,
        mode="tier_ladder",
        min_picks=0,
        max_picks=1,
    )
    second = Pickable.objects.create(name="Tier 2", slot_type=kind)
    with pytest.raises(ValidationError, match="numeric level"):
        authoring.add_picklist_member(picklist, second)
    with pytest.raises(ValidationError, match="numeric level"):
        authoring.revise(member, level=None)


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


def test_rank_table_for_matches_the_exact_counter_and_refuses_ambiguity():
    xp = Counter.objects.create(name="XP")
    kills = Counter.objects.create(name="Kill Count")
    standard = RankTable.objects.create(name="Standard ranks", counter=xp)
    unrelated = RankTable.objects.create(name="Kill ranks", counter=kills)
    miniature = SimpleNamespace(name="Kora")
    computed = SimpleNamespace(acquired=[], echoed=[])

    empty = _Card([])
    assert rank_table_for(miniature, xp, card=empty, computed=computed) is None

    one = _Card(
        [
            _node("standard", standard, "rank_table"),
            _node("kills", unrelated, "rank_table"),
        ]
    )
    found = rank_table_for(miniature, xp, card=one, computed=computed)
    assert found.rank_table == standard

    variant = RankTable.objects.create(name="Variant ranks", counter=xp)
    two = _Card(
        [
            _node("standard", standard, "rank_table"),
            _node("variant", variant, "rank_table"),
        ]
    )
    with pytest.raises(Refusal, match="more than one rank table"):
        rank_table_for(miniature, xp, card=two, computed=computed)


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


@pytest.mark.parametrize(
    "kind",
    [
        "outcome",
        "augment-carried-item",
        "resolve-advancement",
        "apply-changes",
        "counter-change",
        "remove-picks",
        "recruitment-allowance-rule",
        "rank-allowance-rule",
    ],
)
def test_typed_action_configurations_have_authoring_pages(admin_client, kind):
    assert admin_client.get(f"/n26/authoring/{kind}/").status_code == 200


def test_authoring_forms_build_an_outcome_and_attach_it_to_an_action():
    slot_type = SlotType.objects.create(name="Augmentation")
    operation_form = generate_form(specs()["augment_carried_item"])(
        {"slot_type": str(slot_type.pk)}
    )
    assert operation_form.is_valid(), operation_form.errors
    operation = operation_form.compile()

    outcome_form = generate_form(specs()["create_outcome"])(
        {"name": "Hunting Rig Augmentation", "augment_carried_item": str(operation.pk)}
    )
    assert outcome_form.is_valid(), outcome_form.errors
    outcome = outcome_form.compile()

    action = Action.objects.create(name="Suit evolution", timing="post_cycle")
    member_form = generate_form(specs()["add_action_outcome"])(
        {"outcome": str(outcome.pk), "position": 0}, carrier=action
    )
    assert member_form.is_valid(), member_form.errors
    member = specs()["add_action_outcome"].verb(action, **member_form.verb_data())
    assert member.outcome == outcome


def test_authoring_forms_build_prices_allowances_and_ladder_levels():
    kill_count = Counter.objects.create(name="Kill Count")
    action = Action.objects.create(name="Suit evolution", timing="post_cycle")
    price_form = generate_form(specs()["add_action_price_component"])(
        {
            "resource": "counter",
            "payer": "fighter",
            "counter": str(kill_count.pk),
            "amount": 4,
            "position": 0,
        },
        carrier=action,
    )
    assert price_form.is_valid(), price_form.errors
    price = specs()["add_action_price_component"].verb(action, **price_form.verb_data())
    assert price.counter == kill_count

    allowance_form = generate_form(specs()["rank_allowance_rule"])(
        {"counter": str(kill_count.pk)}
    )
    assert allowance_form.is_valid(), allowance_form.errors
    assert allowance_form.compile().counter == kill_count

    slot_type = SlotType.objects.create(name="Augmentation")
    picklist = Picklist.objects.create(name="Rig tiers", slot_type=slot_type)
    pickable = Pickable.objects.create(name="Tier 1", slot_type=slot_type)
    member_form = generate_form(specs()["add_picklist_member"])(
        {"pickable": str(pickable.pk), "position": 0, "level": 1}, carrier=picklist
    )
    assert member_form.is_valid(), member_form.errors
    member = specs()["add_picklist_member"].verb(picklist, **member_form.verb_data())
    assert member.level == 1
