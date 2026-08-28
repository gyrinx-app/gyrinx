"""The Chaos God conversion, proven on a prod-shaped world.

Two doors, one slot type: a Hidden built into Chaos Helot Cult offers
the Chaos Gods menu, and the Chaos Corrupted affiliation offers the
same menu. After the conversion those are two slot rows of one type,
the four gods are pickables with nothing moved (they have no payload),
and every page still says the same things.
"""

import pytest

from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.conversion import apply, plan_chaos_god
from n26.library.models import Affiliation, Pickable, Slot
from n26.tests.sandbox.actions import (
    assign,
    choose,
    create_affiliation,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_slot_type,
    found_gang,
    modifier,
    offers_choice,
    remove,
    section_of,
    targets_gang,
)

pytestmark = pytest.mark.django_db

GODS = ("Architect of Fate", "Blood God", "Dark Prince", "Plague Lord")


@pytest.fixture
def prod_shape(default_pack):
    return build_prod_shape()


@pytest.fixture
def world(prod_shape, owner):
    return build_world(prod_shape, owner)


def build_prod_shape():
    """The system as production holds it: two Chaos God offers, one
    menu of four gods with no payload, Chaos Corrupted still an
    Affiliation."""
    gods = {name: create_affiliation(name) for name in GODS}
    menu = section_of(
        create_collection("Chaos Gods", entries=[(gods[name], {}) for name in GODS]),
        "Chaos Gods",
        0,
        is_default=True,
    )
    helot_hidden = create_hidden("Chaos God — Helots")
    modifier(
        "Helots: the gang is asked its Chaos God",
        targets_gang(),
        offers_choice(Affiliation, from_section=menu, label="Chaos God"),
        carried_by=helot_hidden,
    )
    helot_type = create_gang_type("Chaos Helot Cult", starting_credits=2000)
    helot_type.built_ins = create_default_set("Helot built-ins", members=[helot_hidden])
    helot_type.save()

    corrupted = create_affiliation("Chaos Corrupted")
    modifier(
        "Chaos Corrupted: the gang is asked its Chaos God",
        targets_gang(),
        offers_choice(Affiliation, from_section=menu, label="Chaos God"),
        carried_by=corrupted,
    )
    house_type = create_gang_type("Escher", starting_credits=2000)

    # Fossils / other systems the conversion must not swap.
    modifier(
        "a detached Chaos God offer",
        targets_gang(),
        offers_choice(Affiliation, from_section=menu, label="Chaos God"),
    )
    variant_hidden = create_hidden("Variant")
    modifier(
        "Offer Variants",
        targets_gang(),
        offers_choice(Affiliation, label="Variant"),
        carried_by=variant_hidden,
    )
    return helot_type, house_type, gods, helot_hidden, corrupted, menu


def build_world(prod_shape, owner):
    helot_type, house_type, gods, helot_hidden, corrupted, _ = prod_shape
    gangs = {
        "helot_unanswered": found_gang(
            "The Unspoken Helots", helot_type, owner=owner, budget=2000
        ),
        "helot_answered": found_gang(
            "The Dedicated Helots", helot_type, owner=owner, budget=2000
        ),
        "corrupted_unanswered": found_gang(
            "The Unnamed Corrupted", house_type, owner=owner, budget=2000
        ),
        "corrupted_answered": found_gang(
            "The Bloodied House", house_type, owner=owner, budget=2000
        ),
        "rechosen": found_gang(
            "The Twice Dedicated", helot_type, owner=owner, budget=2000
        ),
    }

    def helot_line(gang):
        return Assignment.objects.get(hidden=helot_hidden, gang=gang, archived=False)

    choose(helot_line(gangs["helot_answered"]), gods["Dark Prince"])
    assign(corrupted, gang=gangs["corrupted_unanswered"])
    assign(corrupted, gang=gangs["corrupted_answered"])
    choose(
        Assignment.objects.get(
            affiliation=corrupted, gang=gangs["corrupted_answered"], archived=False
        ),
        gods["Blood God"],
    )
    choose(helot_line(gangs["rechosen"]), gods["Plague Lord"])
    remove(
        Assignment.objects.get(
            affiliation=gods["Plague Lord"], gang=gangs["rechosen"], archived=False
        )
    )
    choose(helot_line(gangs["rechosen"]), gods["Architect of Fate"])
    for gang in gangs.values():
        assert_reconciled(gang)
    return gangs, helot_hidden, corrupted


def _helot_slot():
    return Slot.objects.get(name="Chaos God", qualifier="Chaos God — Helots")


def _corrupted_slot():
    return Slot.objects.get(name="Chaos God", qualifier="Chaos Corrupted")


class TestThePlan:
    def test_it_says_everything_it_would_do(self, world):
        plan = plan_chaos_god()

        assert plan.ok and not plan.nothing_here
        said = "\n".join(plan.preview())
        assert "create slot type “Chaos God”, refusing repeats" in said
        assert said.count("create pickable") == 4
        assert "create pickable “Architect of Fate”" in said
        assert "create pickable “Blood God”" in said
        assert "create pickable “Dark Prince”" in said
        assert "create pickable “Plague Lord”" in said
        assert said.count("create slot “Chaos God”") == 2
        assert "pick landing on the gang" in said
        assert "the “Chaos God — Helots” hidden" in said
        assert "the “Chaos Corrupted” affiliation" in said
        assert "made_pickable" not in said
        assert "retire" not in said
        assert "prove " in said
        assert "reconcile all" in said

    def test_it_rewrites_the_archived_answer_too(self, world):
        said = "\n".join(plan_chaos_god().preview())
        # Three live answers (helot Dark Prince, corrupted Blood God,
        # rechosen Architect of Fate) plus the rechosen gang's archived
        # Plague Lord.
        assert said.count("rewrite pick") >= 4

    def test_an_archived_gang_is_rewritten_but_not_held(self, world):
        """Archived gangs still have their picks moved, but a stale
        archived gang must not lock or refuse the whole conversion."""
        gangs, _, _ = world
        gone = gangs["helot_answered"]
        gone.archive()

        plan = plan_chaos_god()

        assert gone.pk not in plan.holder_ids
        apply(plan)
        pick = Assignment.objects.get(gang=gone, pickable__isnull=False, archived=False)
        assert pick.pickable.name == "Dark Prince"

    def test_nothing_here_when_the_system_is_absent(self, default_pack):
        plan = plan_chaos_god()

        assert plan.nothing_here
        assert apply(plan) == plan.preview()

    def test_a_hidden_that_shares_the_slot_name_is_told_apart_by_kind(
        self, owner, default_pack
    ):
        """Production's Helot hidden is called Chaos God, the same word
        as the slot. The two slot rows still need distinct qualifiers."""
        shape = build_prod_shape()
        _, _, _, helot_hidden, _, _ = shape
        helot_hidden.name = "Chaos God"
        helot_hidden.save()
        build_world(shape, owner)

        plan = plan_chaos_god()

        assert plan.ok
        said = "\n".join(plan.preview())
        assert "told apart as “Hidden”" in said
        assert "told apart as “Chaos Corrupted”" in said
        apply(plan)
        assert Slot.objects.filter(name="Chaos God", qualifier="Hidden").exists()
        assert Slot.objects.filter(
            name="Chaos God", qualifier="Chaos Corrupted"
        ).exists()


class TestTheApply:
    def test_every_page_reads_the_same(self, world):
        gangs, _, _ = world
        before = {key: gang_state(g) for key, g in gangs.items()}

        apply(plan_chaos_god())

        for key, gang in gangs.items():
            assert differences(before[key], gang_state(gang)) == []
            assert_reconciled(gang)

    def test_a_helot_pick_lands_on_the_helots_slot(self, world):
        gangs, _, _ = world

        apply(plan_chaos_god())

        pick = Assignment.objects.get(
            gang=gangs["helot_answered"], pickable__isnull=False, archived=False
        )
        assert pick.pickable.name == "Dark Prince"
        assert pick.affiliation_id is None
        assert pick.chosen_for_slot == _helot_slot()
        assert pick.miniature_id is None
        assert pick.chosen_for_id == pick.caused_by_id

    def test_a_corrupted_pick_lands_on_the_corrupted_slot(self, world):
        gangs, _, _ = world

        apply(plan_chaos_god())

        pick = Assignment.objects.get(
            gang=gangs["corrupted_answered"],
            pickable__name="Blood God",
            archived=False,
        )
        assert pick.chosen_for_slot == _corrupted_slot()
        assert pick.affiliation_id is None

    def test_chaos_corrupted_stays_an_affiliation(self, world):
        apply(plan_chaos_god())

        assert Affiliation.objects.filter(name="Chaos Corrupted").exists()
        assert not Pickable.objects.filter(name="Chaos Corrupted").exists()

    def test_each_slot_is_labelled_the_way_the_offer_already_was(self, world):
        """The card's own words, carried across rather than guessed."""
        _, hidden, _ = world
        offer = next(
            m
            for m in hidden.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        said = offer.offers_choice.kind_label

        apply(plan_chaos_god())

        assert said == "Chaos God"
        for slot in Slot.objects.filter(name="Chaos God"):
            assert slot.choice_label == said
            assert slot.min_picks == 0
            assert slot.max_picks == 1
            assert slot.assigned_to == Slot.WillBeAssignedTo.GANG
        assert Slot.objects.filter(name="Chaos God").count() == 2

    def test_the_archived_answer_is_rewritten_too(self, world):
        gangs, _, _ = world

        apply(plan_chaos_god())

        archived = Assignment.objects.get(gang=gangs["rechosen"], archived=True)
        assert archived.pickable.name == "Plague Lord"
        assert archived.affiliation_id is None
        assert archived.chosen_for_slot == _helot_slot()

    def test_every_god_is_a_pickable_even_if_nobody_picked_it(self, world):
        # Architect of Fate is picked by the rechosen gang; the other
        # three are covered by live or archived answers. The claim is
        # the menu, not the picks.
        apply(plan_chaos_god())

        for name in GODS:
            assert Pickable.objects.filter(
                name=name, slot_type__name="Chaos God"
            ).exists()

    def test_the_fossils_are_left_standing(self, world):
        from n26.library.models import Modifier

        before = Modifier.objects.filter(name="a detached Chaos God offer").count()
        apply(plan_chaos_god())
        assert (
            Modifier.objects.filter(name="a detached Chaos God offer").count()
            == before
            == 1
        )
        assert Modifier.objects.filter(name="Offer Variants").exists()

    def test_an_unanswered_helot_does_not_nag(self, world):
        gangs, _, _ = world

        apply(plan_chaos_god())

        state = gang_state(gangs["helot_unanswered"])
        assert ("Chaos God", "") in state["choices"]
        assert all("0 of 1" not in note for note in state["notes"])


class TestTheBehaviourThatMustSurvive:
    def test_the_new_machinery_answers_again_on_a_helot(self, world):
        gangs, hidden, _ = world
        apply(plan_chaos_god())
        gang = gangs["helot_unanswered"]
        hidden_line = Assignment.objects.get(hidden=hidden, gang=gang, archived=False)

        choose(
            hidden_line,
            Pickable.objects.get(name="Blood God"),
            slot=_helot_slot(),
        )

        state = gang_state(gang)
        assert ("Chaos God", "Blood God") in state["choices"]
        assert_reconciled(gang)

    def test_the_new_machinery_answers_again_on_chaos_corrupted(self, world):
        gangs, _, corrupted = world
        apply(plan_chaos_god())
        gang = gangs["corrupted_unanswered"]
        line = Assignment.objects.get(affiliation=corrupted, gang=gang, archived=False)

        choose(
            line,
            Pickable.objects.get(name="Dark Prince"),
            slot=_corrupted_slot(),
        )

        state = gang_state(gang)
        assert ("Chaos God", "Dark Prince") in state["choices"]
        assert_reconciled(gang)

    def test_rechoosing_replaces_the_god(self, world):
        gangs, hidden, _ = world
        apply(plan_chaos_god())
        gang = gangs["helot_answered"]
        standing = Assignment.objects.get(
            gang=gang, chosen_for_slot=_helot_slot(), archived=False
        )
        hidden_line = Assignment.objects.get(hidden=hidden, gang=gang, archived=False)

        remove(standing)
        choose(
            hidden_line,
            Pickable.objects.get(name="Plague Lord"),
            slot=_helot_slot(),
        )

        assert ("Chaos God", "Plague Lord") in gang_state(gang)["choices"]
        assert_reconciled(gang)

    def test_a_second_run_is_a_clean_no_op(self, world):
        apply(plan_chaos_god())

        assert plan_chaos_god().nothing_here


class TestTheStory:
    def test_a_god_pick_is_reworded_to_chaos_god(self, world):
        """The story names a pick by its slot type, so a god that used
        to read as an affiliation now reads as a chaos god."""
        from n26.core.history import Sub, _kindword

        gangs, _, _ = world
        apply(plan_chaos_god())

        pick = Assignment.objects.get(
            gang=gangs["helot_answered"], pickable__isnull=False, archived=False
        )
        assert _kindword(pick) == "chaos god"
        assert Sub(name=pick.pickable.name, kind=_kindword(pick)).detail == "chaos god"

        pick = Assignment.objects.get(
            gang=gangs["corrupted_answered"], pickable__name="Blood God", archived=False
        )
        assert _kindword(pick) == "chaos god"


class TestTheRefusals:
    def test_a_standing_slot_type_is_refused(self, world):
        create_slot_type("Chaos God")

        plan = plan_chaos_god()

        assert not plan.ok
        assert any("already stands" in problem for problem in plan.problems)

    def test_a_differently_cased_slot_type_is_refused(self, world):
        create_slot_type("CHAOS GOD")

        plan = plan_chaos_god()

        assert not plan.ok
        assert any("already stands" in problem for problem in plan.problems)

    def test_a_colliding_pickable_is_qualified(self, world):
        from n26.tests.sandbox.actions import create_pickable

        other = create_slot_type("Something Else")
        create_pickable("Blood God", other)

        plan = plan_chaos_god()

        assert plan.ok
        said = "\n".join(plan.preview())
        assert "told apart as “Chaos God”" in said

    def test_a_colliding_qualified_pickable_is_refused(self, world):
        from n26.tests.sandbox.actions import create_pickable

        other = create_slot_type("Something Else")
        create_pickable("Blood God", other)
        create_pickable("Blood God", other, qualifier="Chaos God")

        plan = plan_chaos_god()

        assert not plan.ok
        assert any("already stands" in p for p in plan.problems)

    def test_a_shared_offer_is_refused(self, world, prod_shape):
        from n26.library.authoring import attach_modifiers_to

        _, _, _, helot_hidden, corrupted, _ = prod_shape
        offer = next(
            m
            for m in helot_hidden.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(corrupted, [offer])

        plan = plan_chaos_god()

        assert not plan.ok
        assert any("shared" in p or "carried alone" in p for p in plan.problems)

    def test_an_off_menu_pick_is_refused(self, world, prod_shape):
        _, _, _, helot_hidden, _, _ = prod_shape
        gangs, _, _ = world
        offmenu = create_affiliation("Something Else Entirely")
        line = Assignment.objects.get(
            hidden=helot_hidden, gang=gangs["helot_unanswered"], archived=False
        )
        Assignment.objects.create(
            affiliation=offmenu,
            gang=gangs["helot_unanswered"],
            caused_by=line,
            chosen_for=line,
            gang_root=gangs["helot_unanswered"],
        )

        plan = plan_chaos_god()

        assert not plan.ok
        assert any("the menu does not offer" in p for p in plan.problems)
