"""Planning a built-in change reads every existing use and writes nothing."""

import pytest

from n26.core.built_ins import (
    BuiltInAction,
    plan_built_in_add,
    plan_default_member,
)
from n26.core.models import Assignment, CounterValue, LedgerEvent
from n26.core.operations import operation
from n26.library.authoring import add_default_member
from n26.tests.sandbox.actions import (
    add_built_in,
    assign,
    create_counter,
    create_default_set,
    create_rule,
    create_subtype,
    found_gang,
    hire,
    offer_option,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(owner, gang_type):
    return found_gang("The Bad Girls", gang_type, owner=owner, budget=1000)


@pytest.fixture
def ganger(make_profile):
    return make_profile("Escher Ganger", price=50)


@pytest.fixture
def yolanda(gang, ganger):
    return hire(gang, ganger, "Yolanda", paid=50)


class TestAReadOnlyPlan:
    def test_a_missing_member_would_reach_an_existing_hire(self, ganger, yolanda):
        rule = create_rule("Hot-headed")
        assignments = Assignment.objects.count()
        events = LedgerEvent.objects.count()

        plan = plan_built_in_add(ganger, rule)

        assert len(plan.uses) == 1
        assert plan.uses[0].carrier == yolanda.membership
        assert plan.uses[0].action == BuiltInAction.CREATE
        assert plan.writes == 1
        assert plan.visible_changes == 1
        assert Assignment.objects.count() == assignments
        assert LedgerEvent.objects.count() == events

    @pytest.mark.parametrize(
        "make_thing",
        [create_rule, create_subtype, create_counter],
        ids=["rule", "subtype", "counter"],
    )
    def test_an_independent_fact_already_on_the_model_satisfies_it(
        self, make_thing, ganger, yolanda
    ):
        thing = make_thing(f"Standing {make_thing.__name__}")
        standing = assign(thing, miniature=yolanda)

        plan = plan_built_in_add(ganger, thing)

        assert plan.uses[0].action == BuiltInAction.SATISFIED
        assert plan.uses[0].existing == standing
        assert plan.writes == 0
        assert plan.visible_changes == 0

    def test_a_matching_counter_keeps_its_running_value(self, ganger, yolanda):
        xp = create_counter("XP")
        standing = assign(xp, miniature=yolanda)
        with operation(yolanda.gang, actor=yolanda.gang.owner) as op:
            op.tally(standing, 7)

        plan = plan_built_in_add(ganger, xp)

        assert plan.uses[0].action == BuiltInAction.SATISFIED
        assert CounterValue.objects.get(assignment=standing).value == 7

    def test_an_owner_removal_keeps_a_new_default_hidden(self, ganger, yolanda):
        rule = create_rule("Hot-headed")
        with operation(yolanda.gang, actor=yolanda.gang.owner) as op:
            removal = op.take_away(yolanda, rule)

        plan = plan_built_in_add(ganger, rule)

        assert plan.uses[0].action == BuiltInAction.CREATE
        assert plan.uses[0].removal == removal
        assert plan.writes == 1
        assert plan.visible_changes == 0


class TestStoredMembers:
    def test_explicit_provenance_identifies_the_member_and_its_acquisition(
        self, ganger, gang
    ):
        rule = create_rule("Hot-headed")
        member = add_built_in(ganger, rule)
        yolanda = hire(gang, ganger, "Yolanda", paid=50)
        standing = Assignment.objects.get(
            caused_by=yolanda.membership,
            rule=rule,
            archived=False,
        )
        standing.materialised_from = member
        standing.materialised_for = yolanda.membership
        standing.save(
            update_fields=["materialised_from", "materialised_for", "modified"]
        )

        plan = plan_default_member(member)

        assert plan.uses[0].action == BuiltInAction.MATERIALISED
        assert plan.uses[0].existing == standing
        assert list(member.materialisations.all()) == [standing]
        assert list(yolanda.membership.materialised_defaults.all()) == [standing]

    def test_a_member_materialised_before_provenance_fields_is_recognised(
        self, ganger, gang
    ):
        rule = create_rule("Hot-headed")

        member = add_built_in(ganger, rule)
        yolanda = hire(gang, ganger, "Yolanda", paid=50)
        standing = Assignment.objects.get(
            caused_by=yolanda.membership,
            rule=rule,
            archived=False,
        )
        assert standing.materialised_from_id is None

        plan = plan_default_member(member)

        assert plan.uses[0].action == BuiltInAction.MATERIALISED
        assert plan.uses[0].existing == standing
        assert plan.writes == 0

    def test_a_shared_set_reaches_every_carrier_that_uses_it(self, make_profile, gang):
        shared = create_default_set("Shared vows")
        first = make_profile("First", built_ins=shared)
        second = make_profile("Second", built_ins=shared)
        hire(gang, first, "One")
        hire(gang, second, "Two")

        plan = plan_built_in_add(first, create_rule("Sworn"))

        assert len(plan.uses) == 2
        assert {use.carrier.profile for use in plan.uses} == {first, second}
        assert plan.writes == 2

    def test_an_option_member_reaches_only_acquisitions_that_took_that_set(
        self, make_profile, gang
    ):
        profile = make_profile("Khimerix")
        plain = create_default_set("Plain")
        altered = create_default_set("Altered")
        offer_option(profile, "Plain", default_set=plain, position=0)
        offer_option(profile, "Altered", default_set=altered, position=1)
        hire(gang, profile, "Plain one", option=plain)
        changed = hire(gang, profile, "Changed one", option=altered)
        member = add_default_member(altered, create_rule("Unstable"))

        plan = plan_default_member(member)

        assert [use.carrier for use in plan.uses] == [changed.membership]
        assert plan.uses[0].action == BuiltInAction.CREATE
