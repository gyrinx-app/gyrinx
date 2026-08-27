"""The Outcast Affiliation conversion, proven on a prod-shaped world.

A Hidden built into the gang type offers the Affiliations menu; Clan
House chains a second menu of houses. After the conversion those are
slots and pickables, the modifiers have moved not copied, and every
page still says the same things.
"""

import pytest

from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.conversion import apply, plan_outcast_affiliation
from n26.library.models import Affiliation, Pickable, Slot
from n26.tests.sandbox.actions import (
    adds,
    choose,
    create_affiliation,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_profile,
    create_slot_type,
    create_subtype,
    create_wargear,
    found_gang,
    has_subtypes,
    hire,
    modifier,
    offers_choice,
    remove,
    section_of,
    targets_every_model,
    targets_gang,
)

pytestmark = pytest.mark.django_db

HOUSES = ("Cawdor", "Delaque", "Escher", "Goliath", "Van Saar", "Orlock")
AFFILIATIONS = ("Clanless", "Clan House", "Mutant", "Aranthian")


@pytest.fixture
def prod_shape(default_pack, person_type):
    return build_prod_shape(person_type)


@pytest.fixture
def world(prod_shape, owner):
    return build_world(prod_shape, owner)


def build_prod_shape(person_type):
    """The system as production holds it: a Hidden offering Affiliation,
    four affiliations, Clan House chaining the six houses."""
    subtypes = {
        "leader": create_subtype("Outcast Leader"),
        "champion": create_subtype("Outcast Champion"),
        "ganger": create_subtype("Outcast Ganger"),
    }
    leaders_and_champions = [subtypes["leader"], subtypes["champion"]]
    houses = {
        house: create_affiliation(
            f"House {house}",
            effects=[
                (
                    targets_every_model(has_subtypes(*leaders_and_champions)),
                    adds(
                        create_collection(
                            f"House {house} Equipment List",
                            entries=[(create_wargear(f"{house} blade"), {})],
                        )
                    ),
                )
            ],
        )
        for house in HOUSES
    }
    house_section = section_of(
        create_collection("Clan Houses", entries=[(houses[h], {}) for h in HOUSES]),
        "Clan Houses",
        0,
        is_default=True,
    )
    top = {
        "Clanless": create_affiliation("Clanless Outcast"),
        "Clan House": create_affiliation("Clan House Outcast"),
        "Mutant": create_affiliation(
            "Mutant Outcast",
            effects=[
                (
                    targets_every_model(),
                    adds(
                        create_collection(
                            "Mutations",
                            entries=[(create_wargear("Extra Arm", price=30), {})],
                        )
                    ),
                )
            ],
        ),
        "Aranthian": create_affiliation(
            "Aranthian Outcast",
            effects=[
                (
                    targets_every_model(has_subtypes(*leaders_and_champions)),
                    adds(create_collection("Aranthian Equipment List")),
                )
            ],
        ),
    }
    modifier(
        "Clan House: choose one of the six Houses",
        targets_gang(),
        offers_choice(Affiliation, from_section=house_section, label="clan house"),
        carried_by=top["Clan House"],
    )
    # Fossils: unattached offers the conversion must not swap.
    modifier(
        "a whole-kind Affiliation offer",
        targets_gang(),
        offers_choice(Affiliation, label="affiliation"),
    )
    modifier(
        "Corruption",
        targets_gang(),
        offers_choice(Affiliation, label="corruption"),
    )
    menu = section_of(
        create_collection(
            "Affiliations", entries=[(top[name], {}) for name in AFFILIATIONS]
        ),
        "Affiliations",
        0,
        is_default=True,
    )
    hidden = create_hidden("Affiliation")
    modifier(
        "Outcasts: the Leader chooses an Affiliation",
        targets_gang(),
        offers_choice(Affiliation, from_section=menu, label="affiliation"),
        carried_by=hidden,
    )
    gang_type = create_gang_type("Outcasts", starting_credits=2000)
    gang_type.built_ins = create_default_set("Outcast built-ins", members=[hidden])
    gang_type.save()
    profiles = {}
    for rank, name, price in [
        ("leader", "Outcast Leader", 100),
        ("champion", "Outcast Champion", 80),
        ("ganger", "Outcast Ganger", 30),
    ]:
        profile = create_profile(name, person_type, gang_type, price=price)
        profile.built_ins = create_default_set(
            f"{name} built-ins", members=[subtypes[rank]]
        )
        profile.save()
        profiles[rank] = profile
    return gang_type, top, houses, hidden, profiles, subtypes


def build_world(prod_shape, owner):
    gang_type, top, houses, hidden, profiles, _ = prod_shape
    gangs = {
        "unanswered": found_gang("The Unspoken", gang_type, owner=owner, budget=2000),
        "clanless": found_gang("The Clanless", gang_type, owner=owner, budget=2000),
        "open_house": found_gang("The Unhoused", gang_type, owner=owner, budget=2000),
        "housed": found_gang("The Cawdor Kin", gang_type, owner=owner, budget=2000),
        "rechosen": found_gang("The Twice Told", gang_type, owner=owner, budget=2000),
        "mutant": found_gang("The Changed", gang_type, owner=owner, budget=2000),
    }
    fighters = {}
    for key in ("housed", "mutant"):
        fighters[key] = {
            rank: hire(
                gangs[key], profiles[rank], rank.title(), paid=profiles[rank].price
            )
            for rank in ("leader", "champion", "ganger")
        }

    def hidden_line(gang):
        return Assignment.objects.get(hidden=hidden, gang=gang, archived=False)

    choose(hidden_line(gangs["clanless"]), top["Clanless"])
    choose(hidden_line(gangs["open_house"]), top["Clan House"])
    choose(hidden_line(gangs["housed"]), top["Clan House"])
    choose(
        Assignment.objects.get(
            affiliation=top["Clan House"], gang=gangs["housed"], archived=False
        ),
        houses["Cawdor"],
    )
    choose(hidden_line(gangs["mutant"]), top["Mutant"])
    choose(hidden_line(gangs["rechosen"]), top["Clanless"])
    remove(
        Assignment.objects.get(
            affiliation=top["Clanless"], gang=gangs["rechosen"], archived=False
        )
    )
    choose(hidden_line(gangs["rechosen"]), top["Mutant"])
    return gangs, fighters, hidden


def _story(acts):
    told = []
    for act in acts:
        told.append("".join(span.text for span in act.spans))
        told.extend(f"{sub.name}|{sub.kind}|{sub.note}" for sub in act.subs)
    return told


def _lists_of(miniature):
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute

    card = build_card(miniature)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return [c.name for c in compute(card, index).collections]


class TestThePlan:
    def test_it_says_everything_it_would_do(self, world):
        plan = plan_outcast_affiliation()

        assert plan.ok and not plan.nothing_here
        said = "\n".join(plan.preview())
        assert "create slot type “Affiliation”, refusing repeats" in said
        assert "create slot type “Clan House”, refusing repeats" in said
        assert said.count("create pickable") == 10
        assert "create pickable “Clanless Outcast”" in said
        assert "create pickable “House Goliath”" in said
        assert "create slot “Affiliation”" in said
        assert "create slot “Clan House”" in said
        assert "pick landing on the gang" in said
        assert "the “Affiliation” hidden" in said
        assert "the “Clan House Outcast” pickable" in said
        assert "retire" not in said
        assert "prove " in said
        assert "reconcile all" in said

    def test_it_rewrites_the_archived_answer_too(self, world):
        said = "\n".join(plan_outcast_affiliation().preview())
        # Five live answers (clanless, open house, housed top, housed
        # house, mutant) plus the rechosen gang's live Mutant and its
        # archived Clanless.
        assert said.count("rewrite pick") >= 7

    def test_nothing_here_when_the_system_is_absent(self, default_pack):
        plan = plan_outcast_affiliation()

        assert plan.nothing_here
        assert apply(plan) == plan.preview()


class TestTheApply:
    def test_every_page_reads_the_same(self, world):
        gangs, _, _ = world
        before = {key: gang_state(g) for key, g in gangs.items()}

        apply(plan_outcast_affiliation())

        for key, gang in gangs.items():
            assert differences(before[key], gang_state(gang)) == []
            assert_reconciled(gang)

    def test_the_pick_still_lands_on_the_gang(self, world):
        gangs, _, _ = world

        apply(plan_outcast_affiliation())

        pick = Assignment.objects.get(
            gang=gangs["clanless"], pickable__isnull=False, archived=False
        )
        assert pick.pickable.name == "Clanless Outcast"
        assert pick.affiliation_id is None
        assert pick.chosen_for_slot == Slot.objects.get(name="Affiliation")
        assert pick.miniature_id is None
        assert pick.chosen_for_id == pick.caused_by_id

    def test_the_house_pick_lands_on_the_clan_house_slot(self, world):
        gangs, _, _ = world

        apply(plan_outcast_affiliation())

        pick = Assignment.objects.get(
            gang=gangs["housed"], pickable__name="House Cawdor", archived=False
        )
        assert pick.chosen_for_slot == Slot.objects.get(name="Clan House")
        assert pick.affiliation_id is None

    def test_the_archived_answer_is_rewritten_too(self, world):
        gangs, _, _ = world

        apply(plan_outcast_affiliation())

        archived = Assignment.objects.get(gang=gangs["rechosen"], archived=True)
        assert archived.pickable.name == "Clanless Outcast"
        assert archived.affiliation_id is None
        assert archived.chosen_for_slot == Slot.objects.get(name="Affiliation")

    def test_house_goliath_is_a_pickable_even_though_nobody_picked_it(self, world):
        apply(plan_outcast_affiliation())

        assert Pickable.objects.filter(name="House Goliath").exists()

    def test_the_fossils_are_left_standing(self, world):
        from n26.library.models import Modifier

        before = Modifier.objects.filter(name="a whole-kind Affiliation offer").count()
        apply(plan_outcast_affiliation())
        assert (
            Modifier.objects.filter(name="a whole-kind Affiliation offer").count()
            == before
            == 1
        )
        assert Modifier.objects.filter(name="Corruption").exists()


class TestTheBehaviourThatMustSurvive:
    def test_the_house_list_still_opens_to_the_right_ranks(self, world):
        _, fighters, _ = world
        before = {
            rank: _lists_of(fighters["housed"][rank])
            for rank in ("leader", "champion", "ganger")
        }
        assert "House Cawdor Equipment List" in before["leader"]
        assert "House Cawdor Equipment List" in before["champion"]
        assert "House Cawdor Equipment List" not in before["ganger"]

        apply(plan_outcast_affiliation())

        for rank, was in before.items():
            assert _lists_of(fighters["housed"][rank]) == was

    def test_mutants_still_open_the_mutation_list_to_every_rank(self, world):
        _, fighters, _ = world
        before = [_lists_of(m) for m in fighters["mutant"].values()]

        apply(plan_outcast_affiliation())

        after = [_lists_of(m) for m in fighters["mutant"].values()]
        assert after == before
        assert all("Mutations" in lists for lists in after)

    def test_the_chain_still_opens_and_closes(self, world, prod_shape):
        gangs, _, hidden = world
        apply(plan_outcast_affiliation())
        gang = gangs["clanless"]
        hidden_line = Assignment.objects.get(hidden=hidden, gang=gang, archived=False)
        affiliation = Slot.objects.get(name="Affiliation")
        house = Slot.objects.get(name="Clan House")

        def standing():
            return Assignment.objects.get(
                gang=gang,
                chosen_for_slot=affiliation,
                archived=False,
            )

        remove(standing())
        choose(
            hidden_line,
            Pickable.objects.get(name="Clan House Outcast"),
            slot=affiliation,
        )
        assert ("Clan house", "") in gang_state(gang)["choices"]

        choose(
            Assignment.objects.get(
                gang=gang, pickable__name="Clan House Outcast", archived=False
            ),
            Pickable.objects.get(name="House Escher"),
            slot=house,
        )
        assert ("Clan house", "House Escher") in gang_state(gang)["choices"]

        remove(standing())
        choose(
            hidden_line,
            Pickable.objects.get(name="Mutant Outcast"),
            slot=affiliation,
        )
        assert all(label != "Clan house" for label, _ in gang_state(gang)["choices"])
        assert_reconciled(gang)
        assert_reconciled(gang)


class TestTheStory:
    def test_affiliation_keeps_its_kind_word(self, world):
        from n26.core.history import _kindword

        gangs, _, _ = world
        apply(plan_outcast_affiliation())

        pick = Assignment.objects.get(
            gang=gangs["clanless"], pickable__isnull=False, archived=False
        )
        assert _kindword(pick) == "affiliation"

    def test_a_house_pick_is_reworded_to_clan_house(self, world):
        from n26.core.history import _kindword

        gangs, _, _ = world
        apply(plan_outcast_affiliation())

        pick = Assignment.objects.get(
            gang=gangs["housed"], pickable__name="House Cawdor", archived=False
        )
        assert _kindword(pick) == "clan house"

    def test_a_clanless_gangs_story_does_not_move(self, world):
        from n26.core import history

        gangs, _, _ = world
        said = _story(history.build(gangs["clanless"]))

        apply(plan_outcast_affiliation())

        assert _story(history.build(gangs["clanless"])) == said


class TestRechoosing:
    def test_the_new_machinery_answers_again(self, world, prod_shape):
        gangs, _, hidden = world
        apply(plan_outcast_affiliation())
        gang = gangs["unanswered"]
        hidden_line = Assignment.objects.get(hidden=hidden, gang=gang, archived=False)

        choose(
            hidden_line,
            Pickable.objects.get(name="Aranthian Outcast"),
            slot=Slot.objects.get(name="Affiliation"),
        )

        state = gang_state(gang)
        assert ("Affiliation", "Aranthian Outcast") in state["choices"]
        assert_reconciled(gang)

    def test_a_second_run_is_a_clean_no_op(self, world):
        apply(plan_outcast_affiliation())

        assert plan_outcast_affiliation().nothing_here


class TestTheRefusals:
    def test_a_standing_slot_type_is_refused(self, world):
        create_slot_type("Affiliation")

        plan = plan_outcast_affiliation()

        assert not plan.ok
        assert any("already stands" in problem for problem in plan.problems)

    def test_a_differently_cased_slot_type_is_refused(self, world):
        create_slot_type("AFFILIATION")

        plan = plan_outcast_affiliation()

        assert not plan.ok
        assert any("already stands" in problem for problem in plan.problems)

    def test_a_colliding_pickable_is_qualified(self, world):
        from n26.tests.sandbox.actions import create_pickable

        other = create_slot_type("Something Else")
        create_pickable("Clanless Outcast", other)

        plan = plan_outcast_affiliation()

        assert plan.ok
        said = "\n".join(plan.preview())
        assert "told apart as “Affiliation”" in said

    def test_a_colliding_qualified_pickable_is_refused(self, world):
        from n26.tests.sandbox.actions import create_pickable

        other = create_slot_type("Something Else")
        create_pickable("Clanless Outcast", other)
        create_pickable("Clanless Outcast", other, qualifier="Affiliation")

        plan = plan_outcast_affiliation()

        assert not plan.ok
        assert any("already stands" in p for p in plan.problems)

    def test_a_shared_offer_is_refused(self, world, prod_shape):
        from n26.library.authoring import attach_modifiers_to

        _, top, _, hidden, _, _ = prod_shape
        offer = next(
            m
            for m in hidden.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(top["Mutant"], [offer])

        plan = plan_outcast_affiliation()

        assert not plan.ok
        assert any("shared" in p or "Hidden alone" in p for p in plan.problems)

    def test_an_off_menu_pick_is_refused(self, world, prod_shape):
        gang_type, top, houses, hidden, _, _ = prod_shape
        gangs, _, _ = world
        offmenu = create_affiliation("Something Else Entirely")
        line = Assignment.objects.get(
            hidden=hidden, gang=gangs["unanswered"], archived=False
        )
        Assignment.objects.create(
            affiliation=offmenu,
            gang=gangs["unanswered"],
            caused_by=line,
            chosen_for=line,
            gang_root=gangs["unanswered"],
        )

        plan = plan_outcast_affiliation()

        assert not plan.ok
        assert any("the menu does not offer" in p for p in plan.problems)
