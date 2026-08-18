"""The Gang Legacy conversion, proven on a prod-shaped world.

The twelve hunt profiles' one shared archetype offer — labelled
"Gang Legacy", the borrowed kind papered over — becomes one shared
grant of a Gang Legacy slot; the house tokens become pickables carrying
their equipment-list modifiers, moved not copied.

Two things distinguish this world from the other conversions': a
second, unrelated system shares the archetype column (an Outcast-shaped
gang whose picks must not move), and the kind was borrowed — though the
story never says it out loud, so no written history changes at all.
"""

import pytest

from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import attach_modifiers_to
from n26.library.conversion import apply, plan_gang_legacy
from n26.library.models import Archetype, Collection, Pickable, Slot
from n26.tests.sandbox.actions import (
    choose,
    create_archetype,
    create_collection,
    create_gang_type,
    create_profile,
    create_slot_type,
    create_subtype,
    ef_adds,
    found_gang,
    hire,
    modifier,
    offers_choice,
    remove,
    section_of,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def prod_shape(default_pack, person_type):
    return build_prod_shape(person_type)


@pytest.fixture
def world(prod_shape, owner):
    return build_world(prod_shape, owner)


def build_prod_shape(person_type):
    """The system as production holds it: hunt profiles sharing one
    offer over a menu of house tokens, each token carrying one
    equipment-list grant — plus the other system on the same column (an
    Outcast-shaped Leader) and a detached fossil copy of the offer."""
    gang_type = create_gang_type("Venators", starting_credits=2000)
    houses = {}
    for name in ["Cawdor", "Escher", "Goliath", "Van Saar"]:
        token = create_archetype(name)
        kit_list = create_collection(f"{name} Equipment List")
        modifier(
            f"{name}: adds {name} Equipment List",
            targets_model(),
            ef_adds(kit_list),
            carried_by=token,
        )
        houses[name] = token
    menu = create_collection("House Legacies", entries=list(houses.values()))
    section = section_of(menu, "Houses", 0, is_default=True)

    profiles = [
        create_profile(name, person_type, gang_type, price=50)
        for name in ["House Hunt Leader 1", "House Hunter 1", "House Hunter 2"]
    ]
    shared = modifier(
        "the model: offers a choice of archetype from House Legacies",
        targets_model(),
        offers_choice(Archetype, from_section=section, label="Gang Legacy"),
        carried_by=profiles[0],
    )
    for profile in profiles[1:]:
        attach_modifiers_to(profile, [shared])

    # The fossil: a second copy of the offer that nothing carries.
    modifier(
        "House Hunt Leader 1: offers a choice of archetype from House Legacies",
        targets_model(),
        offers_choice(Archetype, from_section=section, label="Gang Legacy"),
    )

    # The other system on the same column: an Outcast-shaped Leader
    # whose own archetype pick lands on the gang and must not move.
    outcasts = create_gang_type("Outcast", starting_credits=2000)
    brawler = create_archetype("Brawler")
    modifier(
        "Brawler: Leader models — Combat is Primary",
        targets_model(),
        ef_adds(create_subtype("Brawler-led")),
        carried_by=brawler,
    )
    leader = create_profile("Leader 1", person_type, outcasts, price=135)
    modifier(
        "Leader 1: chooses the gang's Archetype",
        targets_model(),
        offers_choice(Archetype, label="Archetype", will_be_assigned_to="gang"),
        carried_by=leader,
    )
    return gang_type, houses, profiles, (outcasts, leader, brawler)


def build_world(prod_shape, owner):
    """Three Venator gangs — answered (one house twice over, and a
    doubled click), partly answered, never answered — and one Outcast
    gang whose pick shares the column and stays put."""
    gang_type, houses, profiles, (outcasts, leader, brawler) = prod_shape
    hunt_leader, hunter_1, hunter_2 = profiles

    gangs = {
        "answered": found_gang("The Long Watch", gang_type, owner=owner, budget=2000),
        "partial": found_gang("The Half Made", gang_type, owner=owner, budget=2000),
        "quiet": found_gang("The Unsworn", gang_type, owner=owner, budget=2000),
        "outcast": found_gang("The Cast Out", outcasts, owner=owner, budget=2000),
    }
    fighters = {
        "sworn": hire(gangs["answered"], hunt_leader, "Vex", paid=50),
        "second": hire(gangs["answered"], hunter_1, "Kade", paid=50),
        "third": hire(gangs["answered"], hunter_2, "Mara", paid=50),
        "partial_a": hire(gangs["partial"], hunter_1, "Odo", paid=50),
        "partial_b": hire(gangs["partial"], hunter_2, "Nyx", paid=50),
        "quiet_one": hire(gangs["quiet"], hunter_1, "Sol", paid=50),
        "outcast_leader": hire(gangs["outcast"], leader, "Grim", paid=135),
    }

    def anchor(fighter, profile):
        return Assignment.objects.get(profile=profile, miniature_root=fighter)

    # The answered gang: a re-choice leaving an archived answer, two
    # fighters sworn to one house (ordinary, never a repeat — each
    # fighter answers their own question), and a doubled click.
    choose(anchor(fighters["sworn"], hunt_leader), houses["Cawdor"])
    remove(
        Assignment.objects.get(
            archetype=houses["Cawdor"],
            miniature_root=fighters["sworn"],
            archived=False,
        )
    )
    choose(anchor(fighters["sworn"], hunt_leader), houses["Van Saar"])
    choose(anchor(fighters["second"], hunter_1), houses["Van Saar"])
    choose(anchor(fighters["third"], hunter_2), houses["Escher"])
    choose(
        anchor(fighters["third"], hunter_2), houses["Escher"]
    )  # the same click, twice

    choose(anchor(fighters["partial_a"], hunter_1), houses["Goliath"])

    # The Outcast gang answers its own system's question.
    choose(anchor(fighters["outcast_leader"], leader), brawler)
    return gangs, fighters


class TestThePlan:
    def test_it_says_everything_it_would_do(self, world):
        plan = plan_gang_legacy()

        assert plan.ok and not plan.nothing_here
        said = "\n".join(plan.preview())
        assert "create slot type “Gang Legacy”, refusing repeats" in said
        assert said.count("create pickable") == 4
        assert "moving 1 modifier" in said
        assert "create picklist “House Legacies”" in said
        assert "replace the shared" in said
        assert "the 3 hunt profiles" in said
        # Four live Venator answers move. The archived re-choice, the
        # doubled click's spare, and the Outcast gang's pick all stay.
        assert said.count("rewrite pick") == 4
        assert "leave 1 spare assignment exactly as they are" in said
        # Three gangs hold the carrying profiles; the Outcast gang is
        # not reached — no step can touch it.
        assert "prove 3 of 3 reached gangs read the same, or refuse" in said

    def test_it_deletes_nothing(self, world):
        said = "\n".join(plan_gang_legacy().preview())

        assert "retire" not in said

    def test_a_standing_pilot_is_refused(self, world):
        create_slot_type("Gang Legacy")

        plan = plan_gang_legacy()

        assert not plan.ok
        assert any("retire the pilot first" in problem for problem in plan.problems)


class TestTheApply:
    def test_every_page_reads_the_same(self, world):
        gangs, _ = world
        before = {key: gang_state(g) for key, g in gangs.items()}

        apply(plan_gang_legacy())

        for key, gang in gangs.items():
            assert differences(before[key], gang_state(gang)) == []
            assert_reconciled(gang)

    def test_the_live_answer_moves_and_the_archived_one_stays(self, world):
        gangs, fighters = world

        apply(plan_gang_legacy())

        live = Assignment.objects.get(
            miniature_root=fighters["sworn"], pickable__isnull=False, archived=False
        )
        assert live.pickable.name == "Van Saar"
        assert live.archetype_id is None
        assert live.chosen_for_id == live.caused_by_id
        assert live.chosen_for_slot == Slot.objects.get(name="Gang Legacy")

        archived = Assignment.objects.get(
            miniature_root=fighters["sworn"], archived=True, archetype__isnull=False
        )
        assert archived.archetype.name == "Cawdor"
        assert archived.pickable_id is None
        assert_reconciled(gangs["answered"])

    def test_the_other_system_on_the_column_is_untouched(self, world):
        """The Outcast pick shares the archetype column and nothing
        else; the conversion must not even look at it."""
        gangs, _ = world

        apply(plan_gang_legacy())

        untouched = Assignment.objects.get(
            gang_root=gangs["outcast"], archetype__isnull=False, archived=False
        )
        assert untouched.archetype.name == "Brawler"
        assert untouched.pickable_id is None
        assert Archetype.objects.filter(name="Brawler").exists()

    def test_a_doubled_answer_keeps_its_spare_untouched(self, world):
        gangs, fighters = world
        before = gang_state(gangs["answered"])

        plan = plan_gang_legacy()
        apply(plan)

        assert plan.left_alone == 1
        assert differences(before, gang_state(gangs["answered"])) == []
        spare = Assignment.objects.get(
            miniature_root=fighters["third"], archetype__isnull=False, archived=False
        )
        assert spare.archetype.name == "Escher"
        assert spare.pickable_id is None

    def test_the_house_list_still_arrives_with_the_pick(self, world):
        """The pickable carries the moved equipment-list modifier, so a
        sworn fighter's access reads the same — proven by the page
        parity above, and pinned here on the modifier itself."""
        _, fighters = world

        apply(plan_gang_legacy())

        pickable = Pickable.objects.get(name="Van Saar")
        assert [type(m.effect).__name__ for m in pickable.modifiers.all()] == [
            "AddsAssignable"
        ]
        emptied = Archetype.objects.get(name="Van Saar")
        assert not emptied.modifiers.exists()
        assert Collection.objects.filter(name="Van Saar Equipment List").exists()

    def test_the_story_already_written_says_the_same_words(self, world):
        """These picks stand in the story as their own acts ("gained
        Van Saar on Vex") and never draw a kind word, so the borrowed
        kind was never said out loud — and the conversion changes no
        written word at all. Where a surface does ask a pick its sort,
        the answer becomes the card's word."""
        from n26.core import history
        from n26.core.history import _kindword

        gangs, _ = world
        said = _story(history.build(gangs["answered"]))

        apply(plan_gang_legacy())

        assert _story(history.build(gangs["answered"])) == said
        assert any("Van Saar" in line for line in said)
        pick = Assignment.objects.filter(
            pickable__isnull=False, gang_root=gangs["answered"]
        ).first()
        assert _kindword(pick) == "gang legacy"

    def test_rechoosing_works_on_the_new_machinery(self, world, prod_shape):
        _, _, profiles, _ = prod_shape
        gangs, fighters = world
        apply(plan_gang_legacy())
        anchor = Assignment.objects.get(
            profile=profiles[1], miniature_root=fighters["partial_a"]
        )

        remove(
            Assignment.objects.get(
                pickable__name="Goliath", miniature_root=fighters["partial_a"]
            )
        )
        choose(
            anchor,
            Pickable.objects.get(name="Cawdor"),
            slot=Slot.objects.get(name="Gang Legacy"),
            miniature=fighters["partial_a"],
        )

        state = gang_state(gangs["partial"])
        card = state["models"][str(fighters["partial_a"].pk)]
        assert ("Gang Legacy", "Cawdor") in card["choices"]
        assert_reconciled(gangs["partial"])

    def test_a_second_run_is_a_clean_no_op(self, world):
        apply(plan_gang_legacy())

        assert plan_gang_legacy().nothing_here


class TestTheRefusals:
    def test_a_second_carried_offer_wearing_the_label_is_refused(
        self, world, prod_shape
    ):
        _, _, profiles, _ = prod_shape
        menu = Collection.objects.get(name="House Legacies")
        modifier(
            "another Gang Legacy offer",
            targets_model(),
            offers_choice(
                Archetype,
                from_section=menu.sections.first(),
                label="Gang Legacy",
            ),
            carried_by=profiles[2],
        )

        plan = plan_gang_legacy()

        assert not plan.ok
        assert any("expected one" in problem for problem in plan.problems)

    def test_an_offer_carried_off_a_profile_is_refused(self, world):
        from n26.library.conversion.base import carriers_of
        from n26.library.models import Modifier

        offer = next(
            m
            for m in Modifier.objects.filter(offers_choice__isnull=False)
            if m.offers_choice.label == "Gang Legacy" and carriers_of(m)
        )
        attach_modifiers_to(create_subtype("Bystander"), [offer])

        plan = plan_gang_legacy()

        assert not plan.ok
        assert any("not profiles" in problem for problem in plan.problems)

    def test_a_surviving_name_squatter_is_refused(self, world, prod_shape):
        """A stray pickable wearing a house's name — a pilot remnant, a
        hand experiment — would turn a valid-looking plan into a
        mid-apply integrity error. The plan refuses it in words."""
        from n26.tests.sandbox.actions import create_pickable

        other_type = create_slot_type("Something Else")
        create_pickable("Cawdor", other_type)

        plan = plan_gang_legacy()

        assert not plan.ok
        assert any("already wear these names" in problem for problem in plan.problems)

    def test_a_pick_the_menu_does_not_offer_is_refused(self, world, prod_shape):
        """A live pick of an off-menu house anchored on a carrying
        profile would keep its line and lose its question when the
        offer is swapped — refused, never stranded."""
        gang_type, houses, profiles, _ = prod_shape
        gangs, fighters = world
        offmenu = create_archetype("Ironhead Squat")
        line = Assignment.objects.get(
            profile=profiles[1], miniature_root=fighters["quiet_one"]
        )
        Assignment.objects.create(
            archetype=offmenu,
            miniature=fighters["quiet_one"],
            caused_by=line,
            chosen_for=line,
            gang_root=gangs["quiet"],
        )

        plan = plan_gang_legacy()

        assert not plan.ok
        assert any("the menu does not offer" in problem for problem in plan.problems)

    def test_an_archived_house_is_not_resurrected(self, world, prod_shape):
        """A retired house on the menu must not come back as a live
        pickable — and its standing picks refuse rather than strand."""
        _, houses, _, _ = prod_shape
        houses["Goliath"].archived = True
        houses["Goliath"].save()

        plan = plan_gang_legacy()

        assert not plan.ok
        assert any("Goliath" in problem for problem in plan.problems)

    def test_a_carrier_arriving_after_the_plan_refuses_the_apply(
        self, world, prod_shape
    ):
        """The plan proves the shared offer's carriers, but the world
        can move between plan and apply — a carrier attached since must
        end the run in a refusal, never lose its question silently."""
        from n26.library.conversion import ConversionRefused
        from n26.library.conversion.base import carriers_of
        from n26.library.models import Modifier

        plan = plan_gang_legacy()
        offer = next(
            m
            for m in Modifier.objects.filter(offers_choice__isnull=False)
            if m.offers_choice.label == "Gang Legacy" and carriers_of(m)
        )
        # Another profile of the same gang type: a carrier the plan
        # would have accepted, arriving too late for it to know.
        _, _, profiles, _ = prod_shape
        latecomer = create_profile(
            "House Hunter 3", profiles[0].profile_type, profiles[0].gang_type, price=50
        )
        attach_modifiers_to(latecomer, [offer])

        with pytest.raises(ConversionRefused, match="the world moved"):
            apply(plan)

    def test_a_pick_anchored_off_the_profiles_is_refused(self, world, prod_shape):
        """A house answered from an anchor the plan does not know means
        a page the spread cannot promise to have proven."""
        gang_type, houses, _, (_, leader, _) = prod_shape
        gangs, _ = world
        stray = hire(gangs["outcast"], leader, "Wanderer", paid=135)
        anchor = Assignment.objects.get(profile=leader, miniature_root=stray)
        choose(anchor, houses["Cawdor"])

        plan = plan_gang_legacy()

        assert not plan.ok
        assert any(
            "not one of the profiles carrying the offer" in problem
            for problem in plan.problems
        )


def _story(acts):
    """Every word a gang's history page puts on the screen."""
    told = []
    for act in acts:
        told.append("".join(span.text for span in act.spans))
        told.extend(f"{sub.name}|{sub.kind}|{sub.note}" for sub in act.subs)
    return told
