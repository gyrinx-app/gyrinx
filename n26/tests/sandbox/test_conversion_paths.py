"""The Paths conversion, proven end to end on a prod-shaped world.

Builds the Cawdor Paths system exactly as production holds it — the
"Path" hidden built into the gang type, its gang-scoped offer over the
"Paths" menu, two path affiliations carrying gang rules — plays gangs
against it, and proves the conversion's whole discipline: the plan says
everything, the apply changes no page, the picks are rewritten in
place, choosing still works afterwards, a second run is a no-op, and a
world the plan does not recognise is refused without a single write.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.conversion import ConversionRefused, apply, plan_paths
from n26.library.models import Affiliation, Collection, Pickable, Slot, SlotType
from n26.tests.sandbox.actions import (
    choose,
    create_affiliation,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_profile,
    create_rule,
    ef_adds,
    found_gang,
    hire,
    modifier,
    offers_choice,
    remove,
    section_of,
    targets_gang,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def prod_shape(default_pack):
    """The system as production holds it, names and all."""
    paths = {
        "Path of the Fanatic": ("Fanatic Warriors", "Fanatical"),
        "Path of the Pious": ("Pious Warriors", "Without Number"),
    }
    made = {}
    for name, rules in paths.items():
        made[name] = create_affiliation(
            name,
            effects=[(targets_gang(), ef_adds(create_rule(rule))) for rule in rules],
        )
    menu = create_collection("Paths", entries=list(made.values()))
    section = section_of(menu, "Paths", 0, is_default=True)
    carrier = create_hidden("Path")
    modifier(
        "the gang: offers a choice of affiliation from Paths (Paths)",
        targets_gang(),
        offers_choice(Affiliation, from_section=section, label="Path"),
        carried_by=carrier,
    )
    gang_type = create_gang_type("Cawdor", starting_credits=1000)
    gang_type.built_ins = create_default_set("Cawdor founding", members=[carrier])
    gang_type.save()
    return gang_type, carrier, made


@pytest.fixture
def cawdor_profile(prod_shape, person_type):
    gang_type, _, _ = prod_shape
    return create_profile("Brother", person_type, gang_type, price=50)


@pytest.fixture
def gangs(prod_shape, cawdor_profile, owner):
    """Two gangs with members: one settled on the Pious path, one that
    never picked."""
    gang_type, carrier, paths = prod_shape
    settled = found_gang("The Devout", gang_type, owner=owner, budget=1000)
    open_gang = found_gang("The Waverers", gang_type, owner=owner, budget=1000)
    for gang in (settled, open_gang):
        hire(gang, cawdor_profile, f"Brother of {gang.name}", paid=50)
    anchor = Assignment.objects.get(hidden=carrier, gang=settled)
    choose(anchor, paths["Path of the Pious"])
    return settled, open_gang


class TestThePlan:
    def test_it_says_everything_it_would_do(self, gangs):
        plan = plan_paths()

        assert plan.ok and not plan.nothing_here
        said = "\n".join(plan.preview())
        assert "create slot type “Path”" in said
        assert "create pickable “Path of the Fanatic” (Path), moving 2 modifiers" in (
            said
        )
        assert "create picklist “Paths” offering" in said
        assert "pick landing on the gang" in said
        assert "replace “the gang: offers a choice of affiliation" in said
        assert said.count("rewrite pick") == 1
        assert "retire library.Collection “Paths”" in said
        assert said.count("retire library.Affiliation") == 2
        assert "prove 2 of 2 reached gangs read the same, or refuse" in said

    def test_it_writes_nothing(self, gangs):
        before = Assignment.objects.count()

        plan_paths()

        assert Assignment.objects.count() == before
        assert not SlotType.objects.filter(name="Path").exists()


class TestTheApply:
    def test_every_page_reads_the_same(self, gangs):
        settled, open_gang = gangs
        before = {g.pk: gang_state(g) for g in gangs}

        apply(plan_paths())

        for gang in gangs:
            assert differences(before[gang.pk], gang_state(gang)) == []
            assert_reconciled(gang)

    def test_the_pick_is_rewritten_in_place(self, gangs, prod_shape):
        settled, _ = gangs
        _, carrier, _ = prod_shape
        old = Assignment.objects.get(
            affiliation__name="Path of the Pious", gang=settled
        )

        apply(plan_paths())

        old.refresh_from_db()
        assert old.affiliation_id is None
        assert old.pickable == Pickable.objects.get(name="Path of the Pious")
        assert old.chosen_for_id == old.caused_by_id
        assert old.chosen_for == Assignment.objects.get(hidden=carrier, gang=settled)
        assert old.chosen_for_slot == Slot.objects.get(name="Path")
        # Wherever a surface names what sort of thing this pick is, the
        # word is the slot type's — the same word its old kind carried.
        from n26.core.history import _kindword

        assert _kindword(old) == "path"

    def test_the_old_system_is_gone(self, gangs):
        apply(plan_paths())

        assert not Affiliation.objects.filter(name__startswith="Path of").exists()
        assert not Collection.objects.filter(name="Paths").exists()

    def test_the_report_says_what_happened(self, gangs):
        report = apply(plan_paths())

        assert report[-1] == "[paths] applied; every page reads the same"

    def test_rechoosing_works_on_the_new_machinery(self, gangs, prod_shape):
        settled, _ = gangs
        _, carrier, _ = prod_shape
        apply(plan_paths())
        anchor = Assignment.objects.get(hidden=carrier, gang=settled)

        remove(Assignment.objects.get(pickable__name="Path of the Pious"))
        choose(
            anchor,
            Pickable.objects.get(name="Path of the Fanatic"),
            slot=Slot.objects.get(name="Path"),
        )

        state = gang_state(settled)
        assert ("Path", "Path of the Fanatic") in state["choices"]
        assert "Fanatical" in state["rules"]
        assert "Without Number" not in state["rules"]
        assert_reconciled(settled)

    def test_a_second_run_is_a_clean_no_op(self, gangs):
        apply(plan_paths())

        plan = plan_paths()

        assert plan.nothing_here
        assert apply(plan) == plan.preview()


class TestTheRefusals:
    def test_a_world_the_plan_does_not_recognise_is_a_problem_not_a_write(
        self, gangs, default_pack
    ):
        create_hidden("Path", qualifier="an impostor")

        plan = plan_paths()

        assert not plan.ok
        assert "expected one" in plan.problems[0]
        with pytest.raises(ConversionRefused):
            apply(plan)
        assert not SlotType.objects.filter(name="Path").exists()

    def test_a_pick_anchored_on_the_wrong_row_is_refused(
        self, gangs, prod_shape, owner
    ):
        """A hand-made pick whose cause is not the offer's carrier
        answers a question this slot does not ask. The plan names it and
        refuses; nothing is written."""
        from n26.tests.sandbox.actions import assign

        gang_type, carrier, paths = prod_shape
        _, open_gang = gangs
        stray = assign(paths["Path of the Fanatic"], gang=open_gang)
        stray.caused_by = Assignment.objects.get(
            gang_type__isnull=False, gang=open_gang
        )
        stray.save()

        plan = plan_paths()

        assert not plan.ok
        assert any("other than the carrier" in problem for problem in plan.problems)
        with pytest.raises(ConversionRefused):
            apply(plan)
        assert not SlotType.objects.filter(name="Path").exists()
        stray.refresh_from_db()
        assert stray.affiliation == paths["Path of the Fanatic"]

    def test_a_shared_offer_is_a_problem_not_a_silent_detach(
        self, gangs, prod_shape, default_pack
    ):
        """The offer modifier is deleted, so a second carrier would
        silently lose its question — and its gangs sit outside the
        proof. Shared is refused."""
        from n26.library.authoring import attach_modifiers_to

        _, carrier, _ = prod_shape
        offer = next(
            m
            for m in carrier.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(create_hidden("Another door"), [offer])

        plan = plan_paths()

        assert not plan.ok
        assert "shared" in plan.problems[0]


class TestAGangThatSwitchedItsPath:
    """A taken-back pick is archived, not deleted, and still names the
    affiliation — left behind it would PROTECT the retirement. It is
    rewritten like the live one, so the history stays coherent."""

    def test_the_archived_pick_is_rewritten_and_the_retirement_lands(
        self, gangs, prod_shape
    ):
        settled, _ = gangs
        _, carrier, paths = prod_shape
        anchor = Assignment.objects.get(hidden=carrier, gang=settled)
        remove(Assignment.objects.get(affiliation__isnull=False, gang=settled))
        choose(anchor, paths["Path of the Fanatic"])
        archived = Assignment.objects.get(
            affiliation__name="Path of the Pious", gang=settled, archived=True
        )

        report = apply(plan_paths())

        assert not Affiliation.objects.filter(name__startswith="Path of").exists()
        archived.refresh_from_db()
        assert archived.affiliation_id is None
        assert archived.pickable == Pickable.objects.get(name="Path of the Pious")
        assert archived.archived is True
        live = Assignment.objects.get(pickable__isnull=False, archived=False)
        assert live.pickable.name == "Path of the Fanatic"
        assert report[-1] == "[paths] applied; every page reads the same"
        assert_reconciled(settled)


class TestNothingToConvert:
    def test_an_empty_world_is_nothing_to_convert(self, default_pack):
        plan = plan_paths()

        assert plan.nothing_here
        assert "nothing to convert" in apply(plan)[0]
