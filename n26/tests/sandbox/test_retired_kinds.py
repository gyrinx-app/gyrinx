"""Deleting what the conversions left standing.

A conversion moves a system onto slots and picks and deletes nothing, so
its old machinery is still there afterwards: kind rows with their
modifiers moved away, the menu they were chosen from, the offer that
asked the question. None of it reaches a page any more, which is both
why it can go and how the going is proved — nothing a reader is told may
move.
"""

import pytest

from n26.core.capture import gang_state
from n26.core.models import Assignment
from n26.library.authoring import add_section
from n26.library.conversion import apply as apply_conversion
from n26.library.conversion import plan_specialisation
from n26.library.conversion.archived import apply_archived, plan_archived
from n26.library.models import (
    Collection,
    CollectionEntry,
    Hidden,
    Modifier,
    Profile,
    Specialisation,
)
from n26.library.retired_kinds import Refused, apply, find
from n26.tests.sandbox.actions import (
    add_built_in,
    add_entry,
    choose,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_profile,
    create_skill,
    create_specialisation,
    create_subtype,
    ef_adds,
    found_gang,
    hire,
    modifier,
    offers_choice,
    remove,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def converted(default_pack, person_type, owner):
    """A specialisation system with a menu, converted, and the answer a
    gang took back swept across — the state this deletion runs in."""
    specs = {}
    for name, skill in [("Sniper", "Precision Shot"), ("Medic", "Medicate")]:
        specs[name] = create_specialisation(name)
        modifier(
            f"{name}: its skill",
            targets_model(),
            ef_adds(create_skill(skill)),
            carried_by=specs[name],
        )
    menu = create_collection("Specialisations")
    section = add_section(menu, "Specialisation")
    for spec in specs.values():
        add_entry(menu, spec)

    specialist = create_subtype("Specialist")
    modifier(
        "Specialist: offers a choice of specialisation",
        targets_model(),
        offers_choice(Specialisation),
        carried_by=specialist,
    )
    # The general offer, narrowed to the menu and hung on a marker
    # nobody holds. A conversion will not touch an offer that names a
    # section, so this is what it leaves behind for the deletion.
    marker = create_hidden("Specialisation Offer")
    modifier(
        "Specialisation Offer: offers a choice of specialisation",
        targets_model(),
        offers_choice(Specialisation, from_section=section),
        carried_by=marker,
    )
    gang_type = create_gang_type("Enforcers", starting_credits=2000)
    profile = create_profile("Patrol Officer", person_type, gang_type, price=50)
    profile.built_ins = create_default_set("Officer kit", members=[specialist])
    profile.save()

    gang = found_gang("The Watch", gang_type, owner=owner, budget=2000)
    fighter = hire(gang, profile, "Vex", paid=50)
    anchor = Assignment.objects.get(subtype=specialist, miniature=fighter)
    choose(anchor, specs["Sniper"])
    remove(Assignment.objects.get(specialisation=specs["Sniper"], miniature=fighter))
    choose(anchor, specs["Medic"])

    apply_conversion(plan_specialisation())
    apply_archived(plan_archived())
    return gang, fighter, specs, menu


class TestWhatItWouldDelete:
    def test_it_names_the_emptied_kinds_the_menu_and_the_offer(self, converted):
        _, _, specs, menu = converted

        fossils = find()

        assert fossils.ok and not fossils.nothing_here
        said = "\n".join(fossils.preview())
        assert "delete the emptied specialisation “Sniper”" in said
        assert "delete the emptied specialisation “Medic”" in said
        assert f"delete the menu “{menu}” and its sections" in said
        assert "Specialisation Offer: offers a choice of specialisation" in said
        assert "delete the marker “Specialisation Offer”" in said
        assert fossils.counts["kind rows"] == 2
        assert fossils.counts["menu entries"] == 2
        assert fossils.counts["menus"] == 1

    def test_a_kind_still_carrying_something_is_left_where_it_is(self, converted):
        _, _, specs, _ = converted
        modifier(
            "Sniper: something new",
            targets_model(),
            ef_adds(create_skill("Overwatch")),
            carried_by=specs["Sniper"],
        )

        fossils = find()

        assert fossils.ok
        assert any(
            "“Sniper” where it is: it still carries 1 modifier" in note
            for note in fossils.left_alone
        )
        assert "delete the emptied specialisation “Sniper”" not in "\n".join(
            fossils.preview()
        )


class TestDeletingIt:
    def test_the_rows_go(self, converted):
        _, _, _, menu = converted

        apply(find())

        assert not Specialisation.objects.exists()
        assert not CollectionEntry.objects.filter(collection=menu).exists()
        assert not Collection.objects.filter(pk=menu.pk).exists()
        assert not Modifier.objects.filter(
            name="Specialisation Offer: offers a choice of specialisation"
        ).exists()
        assert not Hidden.objects.filter(name="Specialisation Offer").exists()

    def test_no_page_moves(self, converted):
        gang, _, _, _ = converted
        before = gang_state(gang)

        apply(find())

        assert gang_state(gang) == before

    def test_the_pick_that_replaced_the_choice_still_stands(self, converted):
        gang, fighter, _, _ = converted

        apply(find())

        drawn = gang_state(gang)["models"][str(fighter.pk)]
        assert ("Specialisation", "Medic") in drawn["choices"]
        assert "Medicate" in drawn["skills"]

    def test_the_answer_the_sweep_moved_is_untouched(self, converted):
        """It is a pick now, so nothing here names it."""
        apply(find())

        taken_back = Assignment.objects.get(archived=True, pickable__isnull=False)
        assert taken_back.pickable.name == "Sniper"

    def test_a_second_run_finds_nothing(self, converted):
        apply(find())

        assert find().nothing_here


class TestWhatItRefuses:
    def test_it_will_not_run_before_the_sweep(self, default_pack, person_type, owner):
        """An answer still naming a kind means the sweep has not run, and
        the kind cannot go while anything names it."""
        spec = create_specialisation("Sniper")
        specialist = create_subtype("Specialist")
        modifier(
            "Specialist: offers a choice of specialisation",
            targets_model(),
            offers_choice(Specialisation),
            carried_by=specialist,
        )
        gang_type = create_gang_type("Enforcers", starting_credits=2000)
        profile = create_profile("Patrol Officer", person_type, gang_type, price=50)
        profile.built_ins = create_default_set("Officer kit", members=[specialist])
        profile.save()
        gang = found_gang("The Watch", gang_type, owner=owner, budget=2000)
        fighter = hire(gang, profile, "Vex", paid=50)
        choose(Assignment.objects.get(subtype=specialist, miniature=fighter), spec)

        fossils = find()

        assert not fossils.ok
        assert any(
            "1 assignment still name “Sniper”" in problem
            for problem in fossils.problems
        )
        with pytest.raises(Refused):
            apply(fossils)

    def test_a_menu_holding_something_live_keeps_its_shape(self, converted):
        _, _, _, menu = converted
        add_entry(menu, create_skill("Nerves"))

        fossils = find()

        assert fossils.ok
        assert any(
            f"the menu “{menu}”: not everything in it names a retired kind" in note
            for note in fossils.left_alone
        )

        apply(fossils)

        assert Collection.objects.filter(pk=menu.pk).exists()
        assert CollectionEntry.objects.filter(collection=menu).count() == 1

    def test_a_marker_a_profile_comes_with_is_left_alone(self, converted):
        """Nobody holding a marker is not the same as nothing naming it:
        it can be part of what a profile arrives with, and deleting it
        would take that away from every future hire."""
        marker = Hidden.objects.get(name="Specialisation Offer")
        add_built_in(Profile.objects.get(name="Patrol Officer"), marker)

        fossils = find()

        assert fossils.ok
        assert any(
            "the marker “Specialisation Offer”: 1 default assignments still name it"
            in note
            for note in fossils.left_alone
        )

        apply(fossils)

        assert Hidden.objects.filter(pk=marker.pk).exists()

    def test_an_offer_somebody_holds_is_left_alone(self, converted):
        """An offer reaches a card through its carrier. Held by a player
        it is a question drawn on their page — unanswerable now, but
        theirs — and taking it away would take a line off that page."""
        _, fighter, _, _ = converted
        marker = Hidden.objects.get(name="Specialisation Offer")
        Assignment.objects.create(
            hidden=marker, miniature=fighter, gang_root=fighter.gang
        )

        fossils = find()

        assert any(
            "the offer on “Specialisation Offer”: somebody holds it" in note
            for note in fossils.left_alone
        )

        apply(fossils)

        assert Hidden.objects.filter(pk=marker.pk).exists()
        assert Modifier.objects.filter(
            name="Specialisation Offer: offers a choice of specialisation"
        ).exists()
