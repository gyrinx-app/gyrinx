"""Deleting emptied Affiliation library rows.

A conversion moves a system onto slots and picks and deletes nothing, so
its old machinery is still there afterwards: kind rows with their
modifiers moved away, the menu they were chosen from, the fossil offers,
the vestigial Hidden. None of it reaches a page any more, which is both
why it can go and how the going is proved — nothing a reader is told may
move.
"""

import pytest

from n26.core.capture import gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import add_section
from n26.library.empty_affiliations import Refused, apply, find
from n26.library.models import (
    Affiliation,
    Collection,
    CollectionEntry,
    Hidden,
    Modifier,
    Slot,
)
from n26.tests.sandbox.actions import (
    add_built_in,
    add_entry,
    choose,
    create_affiliation,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_profile,
    create_skill,
    create_slot,
    create_slot_type,
    create_subtype,
    ef_adds,
    found_gang,
    hire,
    modifier,
    offers_choice,
    targets_gang,
    targets_model,
)

pytestmark = pytest.mark.django_db


def build_leftover_world(person_type, owner):
    """Emptied Affiliation rows, the four menus, two fossil offers, and
    the vestigial Hidden — the state this deletion runs in, after the
    conversions have moved the picks.
    """
    affiliation = create_slot_type(
        "Affiliation", plural_name="Affiliations", allows_repeats=False
    )
    clan_house = create_slot_type(
        "Clan House", plural_name="Clan Houses", allows_repeats=False
    )
    chaos_god = create_slot_type(
        "Chaos God", plural_name="Chaos Gods", allows_repeats=False
    )
    variant = create_slot_type("Variant", plural_name="Variants", allows_repeats=False)
    for slot_type, name, members in (
        (
            affiliation,
            "Affiliations",
            ("Clanless", "Clan House", "Mutant", "Aranthian"),
        ),
        (
            clan_house,
            "Clan Houses",
            ("House Cawdor", "House Delaque", "House Escher"),
        ),
        (chaos_god, "Chaos Gods", ("Blood God", "Dark Prince")),
        (
            variant,
            "Variants",
            ("Chaos Corrupted", "Genestealer Cult Corrupted"),
        ),
    ):
        pickables = [create_pickable(member, slot_type) for member in members]
        create_slot(
            slot_type.name,
            slot_type,
            create_picklist(name, slot_type, members=pickables),
            assigned_to="gang",
            min_picks=0,
            max_picks=1,
        )

    names = {
        "Clanless": create_affiliation("Clanless"),
        "Clan House": create_affiliation("Clan House"),
        "Mutant": create_affiliation("Mutant"),
        "Aranthian": create_affiliation("Aranthian"),
        "House Cawdor": create_affiliation("House Cawdor", qualifier="Affiliation"),
        "None": create_affiliation("None"),
        "Chaos Corrupted": create_affiliation("Chaos Corrupted"),
        "Blood God": create_affiliation("Blood God"),
    }
    menus = {
        "Affiliations": create_collection(
            "Affiliations",
            entries=[
                (names[n], {})
                for n in ("Clanless", "Clan House", "Mutant", "Aranthian")
            ],
        ),
        "Clan House": create_collection(
            "Clan House", entries=[(names["House Cawdor"], {})]
        ),
        "Variants": create_collection(
            "Variants",
            entries=[(names["Chaos Corrupted"], {}), (names["None"], {})],
        ),
        "Chaos Gods": create_collection(
            "Chaos Gods", entries=[(names["Blood God"], {})]
        ),
    }
    affiliations_section = add_section(menus["Affiliations"], "Affiliations")
    modifier(
        "a whole-kind Affiliation offer",
        targets_gang(),
        offers_choice(Affiliation),
    )
    modifier(
        "Corruption",
        targets_gang(),
        offers_choice(
            Affiliation, from_section=affiliations_section, label="Corruption"
        ),
    )

    variant_slot = Slot.objects.get(name="Variant")
    house = create_gang_type("Cawdor", starting_credits=2000)
    grant = modifier(
        "Variants: the gang is asked its Variant",
        targets_gang(),
        ef_adds(variant_slot),
        carried_by=house,
    )
    vestigial = create_hidden("Variant")
    vestigial.modifiers.add(grant)

    profile = create_profile("Cawdor Ganger", person_type, house, price=50)
    profile.built_ins = create_default_set("Ganger kit")
    profile.save()
    gang = found_gang("The Orphans", house, owner=owner, budget=2000)
    hire(gang, profile, "Vex", paid=50)
    return gang, names, menus, vestigial, house


@pytest.fixture
def leftover_world(default_pack, person_type, owner):
    return build_leftover_world(person_type, owner)


class TestWhatItWouldDelete:
    def test_it_names_the_emptied_kinds_the_menus_the_fossils_and_the_hidden(
        self, leftover_world
    ):
        _, names, menus, vestigial, _ = leftover_world

        fossils = find()

        assert fossils.ok and not fossils.nothing_here
        said = "\n".join(fossils.preview())
        assert "delete the emptied affiliation “Clanless”" in said
        assert "delete the emptied affiliation “None”" in said
        assert f"delete the menu “{menus['Affiliations']}” and its sections" in said
        assert f"delete the menu “{menus['Clan House']}” and its sections" in said
        assert "a whole-kind Affiliation offer" in said
        assert "Corruption" in said
        assert f"delete the marker “{vestigial}”, which nothing holds" in said
        assert "those are the new system" in said
        assert fossils.counts["kind rows"] == 8
        assert fossils.counts["menus"] == 4
        assert fossils.counts["markers"] == 1

    def test_a_kind_still_carrying_something_is_left_where_it_is(self, leftover_world):
        _, names, _, _, _ = leftover_world
        modifier(
            "Clanless: something new",
            targets_model(),
            ef_adds(create_skill("Overwatch")),
            carried_by=names["Clanless"],
        )

        fossils = find()

        assert fossils.ok
        assert any(
            "“Clanless” where it is: it still carries 1 modifier" in note
            for note in fossils.left_alone
        )
        assert "delete the emptied affiliation “Clanless”" not in "\n".join(
            fossils.preview()
        )


class TestDeletingIt:
    def test_the_rows_go(self, leftover_world):
        _, _, menus, vestigial, house = leftover_world
        grant = house.modifiers.get()

        apply(find())

        assert not Affiliation.objects.exists()
        assert not Collection.objects.filter(
            pk__in=[menu.pk for menu in menus.values()]
        ).exists()
        assert not Modifier.objects.filter(name="Corruption").exists()
        assert not Modifier.objects.filter(
            name="a whole-kind Affiliation offer"
        ).exists()
        assert not Hidden.objects.filter(pk=vestigial.pk).exists()
        assert Modifier.objects.filter(pk=grant.pk).exists()
        assert house.modifiers.filter(pk=grant.pk).exists()
        assert Slot.objects.filter(name="Variant").exists()

    def test_no_page_moves(self, leftover_world):
        gang, _, _, _, _ = leftover_world
        before = gang_state(gang)

        apply(find())

        assert gang_state(gang) == before
        assert_reconciled(gang)

    def test_a_second_run_finds_nothing(self, leftover_world):
        apply(find())

        assert find().nothing_here

    def test_a_world_with_no_affiliation_rows_is_nothing_here(self, default_pack):
        create_slot_type(
            "Affiliation", plural_name="Affiliations", allows_repeats=False
        )

        fossils = find()

        assert fossils.nothing_here
        assert fossils.ok


class TestWhatItRefuses:
    def test_a_live_assignment_still_naming_an_affiliation_is_a_refusal(
        self, default_pack, person_type, owner
    ):
        spec = create_affiliation("Mutant")
        specialist = create_subtype("Specialist")
        modifier(
            "offers an affiliation",
            targets_model(),
            offers_choice(Affiliation),
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
            "1 assignment still name “Mutant”" in problem
            for problem in fossils.problems
        )
        with pytest.raises(Refused):
            apply(fossils)

    def test_an_archived_assignment_still_naming_an_affiliation_is_a_refusal(
        self, leftover_world
    ):
        """The Variant conversion archives a printed None in place, so
        the Affiliation column still names it. That is not this to
        clear."""
        gang, names, _, _, _ = leftover_world
        Assignment.objects.create(
            affiliation=names["None"],
            gang=gang,
            gang_root=gang,
            archived=True,
        )

        fossils = find()

        assert not fossils.ok
        assert any(
            "assignment" in problem and "None" in problem
            for problem in fossils.problems
        )

    def test_a_menu_holding_something_live_keeps_its_shape(self, leftover_world):
        _, _, menus, _, _ = leftover_world
        menu = menus["Affiliations"]
        add_entry(menu, create_skill("Nerves"))

        fossils = find()

        assert fossils.ok
        assert any(
            f"the menu “{menu}”: not everything in it is going" in note
            for note in fossils.left_alone
        )

        apply(fossils)

        assert Collection.objects.filter(pk=menu.pk).exists()
        assert CollectionEntry.objects.filter(collection=menu).count() == 1

    def test_a_marker_a_profile_comes_with_is_left_alone(self, leftover_world):
        """Nobody holding a marker is not the same as nothing naming it:
        it can be part of what a profile arrives with."""
        gang, _, _, vestigial, _ = leftover_world
        from n26.library.models import Profile

        add_built_in(Profile.objects.get(name="Cawdor Ganger"), vestigial)

        fossils = find()

        assert fossils.ok
        assert any(
            f"the marker “{vestigial}”" in note and "still name it" in note
            for note in fossils.left_alone
        )

        apply(fossils)

        assert Hidden.objects.filter(pk=vestigial.pk).exists()
        assert gang_state(gang)  # still builds


class TestAfterTheConversions:
    """A leftover world built the way the conversions leave it."""

    def test_after_the_outcast_conversion_the_emptied_rows_can_go(
        self, default_pack, person_type, owner
    ):
        from n26.library.conversion import apply as apply_conversion
        from n26.library.conversion import plan_outcast_affiliation
        from n26.tests.sandbox.test_conversion_affiliation import (
            build_prod_shape,
            build_world,
        )

        gangs, _fighters, _hidden = build_world(build_prod_shape(person_type), owner)
        apply_conversion(plan_outcast_affiliation())
        before = {name: gang_state(gang) for name, gang in gangs.items()}

        fossils = find()
        assert fossils.ok and not fossils.nothing_here
        apply(fossils)

        for name, gang in gangs.items():
            assert gang_state(gang) == before[name]
            assert_reconciled(gang)
        assert find().nothing_here
        assert not Assignment.objects.filter(affiliation__isnull=False).exists()
