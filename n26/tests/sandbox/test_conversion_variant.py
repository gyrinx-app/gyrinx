"""The Variant conversion, proven on a prod-shaped world.

One shared offer on the house gang types (and a vestigial Hidden), menu
of three corruptions plus None. Chaos Corrupted already grants the
Chaos God slot. After the conversion that is one optional Variant slot,
the corruptions are pickables with their modifiers moved not copied,
None is archived, and every page still says the same things — a printed
None reading as an unanswered optional slot.
"""

import pytest

from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import attach_modifiers_to
from n26.library.conversion import apply, plan_variant
from n26.library.conversion.base import _canonicalize_unanswered, carriers_of
from n26.library.models import Affiliation, Hidden, Modifier, Pickable, Slot
from n26.tests.sandbox.actions import (
    adds,
    choose,
    create_affiliation,
    create_collection,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_rule,
    create_slot,
    create_slot_type,
    create_subtype,
    found_gang,
    modifier,
    offers_choice,
    remove,
    removes,
    section_of,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
)

pytestmark = pytest.mark.django_db

HOUSE_TYPES = (
    "Cawdor",
    "Delaque",
    "Escher",
    "Goliath",
    "Orlock",
    "Palanite Enforcers",
    "Van Saar",
)
CORRUPTIONS = (
    "Chaos Corrupted",
    "Genestealer Cult Corrupted",
    "Malstrain Corrupted",
)
GODS = ("Architect of Fate", "Blood God", "Dark Prince", "Plague Lord")


@pytest.fixture
def prod_shape(default_pack):
    return build_prod_shape()


@pytest.fixture
def world(prod_shape, owner):
    return build_world(prod_shape, owner)


def build_prod_shape():
    """The system as production holds it after the Chaos God conversion:
    a shared Variant offer on the seven house gang types and a vestigial
    Hidden, three corruptions plus None, Chaos Corrupted granting the
    Chaos God slot rather than offering a choice."""
    god_type = create_slot_type(
        "Chaos God", plural_name="Chaos Gods", allows_repeats=False
    )
    gods = {name: create_pickable(name, god_type) for name in GODS}
    god_slot = create_slot(
        "Chaos God",
        god_type,
        create_picklist("Chaos Gods", god_type, members=[gods[name] for name in GODS]),
        label="Chaos God",
        assigned_to="gang",
        min_picks=0,
        max_picks=1,
        qualifier="Chaos Corrupted",
    )

    brutes = create_subtype("Gang Brute")
    shared_strip = modifier(
        "no Brutes or Pets",
        targets_every_model(),
        removes(brutes),
    )
    affiliations = {}
    for name in CORRUPTIONS:
        row = create_affiliation(
            name,
            effects=[(targets_every_model(), adds(create_rule(f"{name} mark")))],
        )
        attach_modifiers_to(row, [shared_strip])
        affiliations[name] = row
    modifier(
        "Chaos Corrupted: the gang is asked its Chaos God",
        targets_gang(),
        adds(god_slot),
        carried_by=affiliations["Chaos Corrupted"],
    )
    none = create_affiliation("None")
    menu = section_of(
        create_collection(
            "Variants",
            entries=[(affiliations[name], {}) for name in CORRUPTIONS] + [(none, {})],
        ),
        "Variants",
        0,
        is_default=True,
    )

    types = {
        name: create_gang_type(name, starting_credits=2000) for name in HOUSE_TYPES
    }
    offer = modifier(
        "Offer Variants",
        targets_gang_alone(),
        offers_choice(Affiliation, from_section=menu, label="Variant"),
        carried_by=types["Cawdor"],
    )
    for name, gang_type in types.items():
        if name != "Cawdor":
            attach_modifiers_to(gang_type, [offer])
    hidden = create_hidden("Variant")
    attach_modifiers_to(hidden, [offer])

    # Fossils / other systems the conversion must not swap.
    modifier(
        "a detached Variant offer",
        targets_gang(),
        offers_choice(Affiliation, from_section=menu, label="Variant"),
    )
    outcast_hidden = create_hidden("Affiliation")
    modifier(
        "Outcasts: the Leader chooses an Affiliation",
        targets_gang(),
        offers_choice(Affiliation, label="Affiliation"),
        carried_by=outcast_hidden,
    )
    return types, affiliations, none, god_slot, gods, hidden, offer


def build_world(prod_shape, owner):
    types, affiliations, none, god_slot, gods, hidden, _ = prod_shape
    escher = types["Escher"]
    gangs = {
        "unanswered": found_gang("The Untouched", escher, owner=owner, budget=2000),
        "none": found_gang("The Ordinary House", escher, owner=owner, budget=2000),
        "chaos": found_gang("The Unnamed Corrupted", escher, owner=owner, budget=2000),
        "chaos_god": found_gang("The Bloodied House", escher, owner=owner, budget=2000),
        "gsc": found_gang("The Cult", escher, owner=owner, budget=2000),
        "malstrain": found_gang("The Strain", escher, owner=owner, budget=2000),
        "rechosen": found_gang("The Twice Dedicated", escher, owner=owner, budget=2000),
    }

    def line(gang):
        return Assignment.objects.get(gang_type=escher, gang=gang, archived=False)

    choose(line(gangs["none"]), none)
    choose(line(gangs["chaos"]), affiliations["Chaos Corrupted"])
    choose(line(gangs["chaos_god"]), affiliations["Chaos Corrupted"])
    choose(
        Assignment.objects.get(
            affiliation=affiliations["Chaos Corrupted"],
            gang=gangs["chaos_god"],
            archived=False,
        ),
        gods["Blood God"],
        slot=god_slot,
    )
    choose(line(gangs["gsc"]), affiliations["Genestealer Cult Corrupted"])
    choose(line(gangs["malstrain"]), affiliations["Malstrain Corrupted"])
    choose(line(gangs["rechosen"]), none)
    remove(
        Assignment.objects.get(affiliation=none, gang=gangs["rechosen"], archived=False)
    )
    choose(line(gangs["rechosen"]), affiliations["Malstrain Corrupted"])
    for gang in gangs.values():
        assert_reconciled(gang)
    return gangs, hidden, affiliations, none, god_slot


def _variant_slot():
    return Slot.objects.get(name="Variant")


class TestThePlan:
    def test_it_says_everything_it_would_do(self, world):
        plan = plan_variant()

        assert plan.ok and not plan.nothing_here
        said = "\n".join(plan.preview())
        assert "create slot type “Variant”, refusing repeats" in said
        assert said.count("create pickable") == 3
        assert "create pickable “Chaos Corrupted”" in said
        assert "create pickable “Genestealer Cult Corrupted”" in said
        assert "create pickable “Malstrain Corrupted”" in said
        assert "create pickable “None”" not in said
        assert "create slot “Variant”" in said
        assert "pick landing on the gang" in said
        assert "shared" in said
        assert "grant of the “Variant” slot" in said
        assert "the gang types" in said
        assert "the hidden “Variant”" in said
        assert "made_pickable" not in said
        assert "retire" not in said
        assert "prove " in said
        assert "reconcile all" in said

    def test_it_archives_every_none_and_rewrites_the_corruptions(self, world):
        said = "\n".join(plan_variant().preview())
        # Live None, archived None on the rechosen gang, four live
        # corruptions (chaos, chaos_god, gsc, malstrain) plus the
        # rechosen Malstrain, no archived corruption.
        assert said.count("archive pick") == 2
        assert said.count("rewrite pick") >= 5

    def test_an_archived_gang_is_rewritten_but_not_held(self, world):
        """Archived gangs still have their picks moved, but a stale
        archived gang must not lock or refuse the whole conversion."""
        gangs, _, _, _, _ = world
        gone = gangs["chaos"]
        gone.archive()

        plan = plan_variant()

        assert gone.pk not in plan.holder_ids
        apply(plan)
        pick = Assignment.objects.get(gang=gone, pickable__isnull=False, archived=False)
        assert pick.pickable.name == "Chaos Corrupted"

    def test_an_archived_gangs_none_is_archived_but_not_held(self, world):
        gangs, _, _, _, _ = world
        gone = gangs["none"]
        gone.archive()

        plan = plan_variant()

        assert gone.pk not in plan.holder_ids
        apply(plan)
        none_pick = Assignment.objects.get(gang=gone, affiliation__name="None")
        assert none_pick.archived

    def test_nothing_here_when_the_system_is_absent(self, default_pack):
        plan = plan_variant()

        assert plan.nothing_here
        assert apply(plan) == plan.preview()


class TestTheApply:
    def test_every_page_reads_the_same(self, world):
        gangs, _, _, _, _ = world
        before = {key: gang_state(g) for key, g in gangs.items()}

        apply(plan_variant())

        pair = (("Variant", "None"),)
        for key, gang in gangs.items():
            after = gang_state(gang)
            assert (
                differences(
                    _canonicalize_unanswered(before[key], pair),
                    _canonicalize_unanswered(after, pair),
                )
                == []
            )
            assert_reconciled(gang)

    def test_a_none_gang_captures_equal_to_unanswered(self, world):
        gangs, _, _, _, _ = world
        before = gang_state(gangs["none"])
        assert ("Variant", "None") in before["choices"]

        apply(plan_variant())

        after = gang_state(gangs["none"])
        assert ("Variant", "") in after["choices"]
        assert ("Variant", "None") not in after["choices"]
        assert (
            differences(
                _canonicalize_unanswered(before, (("Variant", "None"),)),
                _canonicalize_unanswered(after, (("Variant", "None"),)),
            )
            == []
        )

    def test_an_unanswered_gang_stays_unanswered(self, world):
        gangs, _, _, _, _ = world
        before = gang_state(gangs["unanswered"])

        apply(plan_variant())

        after = gang_state(gangs["unanswered"])
        assert ("Variant", "") in after["choices"]
        assert differences(before, after) == []

    def test_a_corruption_pick_lands_on_the_variant_slot(self, world):
        gangs, _, _, _, _ = world

        apply(plan_variant())

        pick = Assignment.objects.get(
            gang=gangs["chaos_god"],
            pickable__name="Chaos Corrupted",
            archived=False,
        )
        assert pick.affiliation_id is None
        assert pick.chosen_for_slot == _variant_slot()
        assert pick.miniature_id is None
        assert pick.chosen_for_id == pick.caused_by_id

    def test_chaos_corrupted_stays_an_affiliation_and_becomes_a_pickable(self, world):
        apply(plan_variant())

        assert Affiliation.objects.filter(name="Chaos Corrupted").exists()
        assert Pickable.objects.filter(
            name="Chaos Corrupted", slot_type__name="Variant"
        ).exists()
        assert not Pickable.objects.filter(name="None").exists()

    def test_the_slot_is_labelled_the_way_the_offer_already_was(self, world):
        apply(plan_variant())

        slot = _variant_slot()
        assert slot.choice_label == "Variant"
        assert slot.min_picks == 0
        assert slot.max_picks == 1
        assert slot.assigned_to == Slot.WillBeAssignedTo.GANG
        assert Slot.objects.filter(name="Variant").count() == 1

    def test_the_archived_none_stays_archived(self, world):
        gangs, _, _, _, _ = world

        apply(plan_variant())

        archived = Assignment.objects.get(
            gang=gangs["rechosen"], affiliation__name="None"
        )
        assert archived.archived
        assert archived.pickable_id is None

    def test_every_corruption_is_a_pickable_even_if_nobody_picked_it(self, world):
        apply(plan_variant())

        for name in CORRUPTIONS:
            assert Pickable.objects.filter(
                name=name, slot_type__name="Variant"
            ).exists()

    def test_the_fossils_are_left_standing(self, world):
        before = Modifier.objects.filter(name="a detached Variant offer").count()
        apply(plan_variant())
        assert (
            Modifier.objects.filter(name="a detached Variant offer").count()
            == before
            == 1
        )
        assert Modifier.objects.filter(
            name="Outcasts: the Leader chooses an Affiliation"
        ).exists()

    def test_an_unanswered_variant_does_not_nag(self, world):
        gangs, _, _, _, _ = world

        apply(plan_variant())

        state = gang_state(gangs["unanswered"])
        assert ("Variant", "") in state["choices"]
        assert all("0 of 1" not in note for note in state["notes"])
        state = gang_state(gangs["none"])
        assert ("Variant", "") in state["choices"]
        assert all("0 of 1" not in note for note in state["notes"])

    def test_the_vestigial_hidden_is_not_a_door(self, world):
        apply(plan_variant())

        assert Slot.objects.filter(name="Variant").count() == 1
        assert not Slot.objects.filter(name="Variant", qualifier="Hidden").exists()
        assert not Slot.objects.filter(name="Variant", qualifier="Variant").exists()
        hidden = Hidden.objects.get(name="Variant")
        assert all(
            getattr(m, "offers_choice", None) is None for m in hidden.modifiers.all()
        )
        grants = [
            m
            for m in hidden.modifiers.all()
            if getattr(m, "adds_assignable", None) is not None
            and m.adds_assignable.slot_id
        ]
        assert len(grants) == 1
        assert grants[0].adds_assignable.slot == _variant_slot()


class TestTheBehaviourThatMustSurvive:
    def test_chaos_corrupted_holds_the_chaos_god_grant(self, world):
        apply(plan_variant())

        pickable = Pickable.objects.get(name="Chaos Corrupted")
        grants = [
            m
            for m in pickable.modifiers.all()
            if getattr(m, "adds_assignable", None) is not None
            and m.adds_assignable.slot_id
            and m.adds_assignable.slot.slot_type.name == "Chaos God"
        ]
        assert len(grants) == 1
        emptied = Affiliation.objects.get(name="Chaos Corrupted")
        assert grants[0] not in emptied.modifiers.all()

    def test_un_choosing_variant_retracts_the_god(self, world):
        gangs, _, _, _, _ = world
        apply(plan_variant())
        gang = gangs["chaos_god"]
        pick = Assignment.objects.get(
            gang=gang, pickable__name="Chaos Corrupted", archived=False
        )
        god = Assignment.objects.get(
            gang=gang, pickable__slot_type__name="Chaos God", archived=False
        )

        remove(pick)

        assert not Assignment.objects.filter(pk=god.pk, archived=False).exists()
        state = gang_state(gang)
        assert all(kind != "Chaos God" for kind, _ in state["choices"])
        assert ("Variant", "") in state["choices"]
        assert_reconciled(gang)

    def test_a_shared_modifier_stays_one_row(self, world):
        apply(plan_variant())

        shared = Modifier.objects.get(name="no Brutes or Pets")
        holders = carriers_of(shared)
        assert {kind for kind, _ in holders} == {"Pickable"}
        assert {row.name for _, row in holders} == set(CORRUPTIONS)

    def test_the_new_machinery_answers_again(self, world):
        gangs, _, _, _, _ = world
        apply(plan_variant())
        gang = gangs["unanswered"]
        type_line = Assignment.objects.get(
            gang_type=gang.gang_type, gang=gang, archived=False
        )

        choose(
            type_line,
            Pickable.objects.get(name="Malstrain Corrupted"),
            slot=_variant_slot(),
        )

        state = gang_state(gang)
        assert ("Variant", "Malstrain Corrupted") in state["choices"]
        assert_reconciled(gang)

    def test_a_second_run_is_a_clean_no_op(self, world):
        apply(plan_variant())

        assert plan_variant().nothing_here


class TestTheStory:
    def test_a_corruption_pick_is_reworded_to_variant(self, world):
        """The story names a pick by its slot type, so a corruption that
        used to read as an affiliation now reads as a variant."""
        from n26.core.history import Sub, _kindword

        gangs, _, _, _, _ = world
        apply(plan_variant())

        pick = Assignment.objects.get(
            gang=gangs["gsc"], pickable__isnull=False, archived=False
        )
        assert _kindword(pick) == "variant"
        assert Sub(name=pick.pickable.name, kind=_kindword(pick)).detail == "variant"


class TestTheRefusals:
    def test_a_standing_slot_type_is_refused(self, world):
        create_slot_type("Variant")

        plan = plan_variant()

        assert not plan.ok
        assert any("already stands" in problem for problem in plan.problems)

    def test_a_differently_cased_slot_type_is_refused(self, world):
        create_slot_type("VARIANT")

        plan = plan_variant()

        assert not plan.ok
        assert any("already stands" in problem for problem in plan.problems)

    def test_a_colliding_pickable_is_qualified(self, world):
        other = create_slot_type("Something Else")
        create_pickable("Chaos Corrupted", other)

        plan = plan_variant()

        assert plan.ok
        said = "\n".join(plan.preview())
        assert "told apart as “Variant”" in said

    def test_a_colliding_qualified_pickable_is_refused(self, world):
        other = create_slot_type("Something Else")
        create_pickable("Chaos Corrupted", other)
        create_pickable("Chaos Corrupted", other, qualifier="Variant")

        plan = plan_variant()

        assert not plan.ok
        assert any("already stands" in p for p in plan.problems)

    def test_a_second_distinct_variant_offer_is_refused(self, world, prod_shape):
        types, _, _, _, _, _, _ = prod_shape
        extra = create_hidden("Another Variant door")
        modifier(
            "another Variant offer",
            targets_gang(),
            offers_choice(Affiliation, label="Variant"),
            carried_by=extra,
        )

        plan = plan_variant()

        assert not plan.ok
        assert any("second distinct" in p for p in plan.problems)

    def test_an_off_menu_pick_is_refused(self, world, prod_shape):
        types, _, _, _, _, _, _ = prod_shape
        gangs, _, _, _, _ = world
        offmenu = create_affiliation("Something Else Entirely")
        line = Assignment.objects.get(
            gang_type=types["Escher"], gang=gangs["unanswered"], archived=False
        )
        Assignment.objects.create(
            affiliation=offmenu,
            gang=gangs["unanswered"],
            caused_by=line,
            chosen_for=line,
            gang_root=gangs["unanswered"],
        )

        plan = plan_variant()

        assert not plan.ok
        assert any("the menu does not offer" in p for p in plan.problems)
