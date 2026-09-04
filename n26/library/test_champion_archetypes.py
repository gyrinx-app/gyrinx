"""Splitting the Outcast archetypes into a Leader set and a Champion set.

The content is built here with the ids the shipped library carries, so
what the test reshapes is the shape the migration will find. Everything
asserted would still be true with no gang and no fighter: this is about
what the library holds, not what a card reads.
"""

import pytest
from django.apps import apps

from n26.library.authoring import (
    create_category,
    create_collection,
    create_pickable,
    create_picklist,
    create_section,
    create_slot,
    create_slot_type,
    create_subtype,
    ef_adds,
    ef_offers_choice,
    ef_places,
    has_subtypes,
    modifier,
    section_of,
    targets_every_model,
    targets_model,
)
from n26.library.champion_archetypes import (
    ARCHETYPES,
    CHAMPION_SLOT,
    CHAMPION_SUBTYPE,
    CHAMPION_WYRD_POWERS,
    LEADER_OFFER,
    LEADER_SUBTYPE,
    PICKLIST,
    QUALIFIER,
    WYRD_ADDS_TO_CHAMPIONS,
    WYRD_OFFERS_A_POWER,
    WYRD_POWERS_ARE_PRIMARY,
    make_champion_archetypes,
)
from n26.library.models import Modifier, Pickable, Picklist, Slot

pytestmark = pytest.mark.django_db

#: The gang's own Archetype choice, whose pick the Leader makes and the
#: gang holds. Only the Champion's slot is named by id in the module, so
#: this one's is the test's own.
GANG_SLOT = "01M0G9383Y8QY32V4MANZ3VHE3"


@pytest.fixture
def skills(default_pack):
    """The two sections a placement can aim at."""
    collection = create_collection("Skills & Powers")
    return {
        "primary": section_of(collection, "Primary", 0),
        "secondary": section_of(collection, "Secondary", 1),
    }


@pytest.fixture
def sets(default_pack):
    heading = create_section("Skills")
    return {
        name: create_category(heading, name) for name in ("Combat", "Savant", "Cunning")
    } | {"Wyrd Powers": create_category(create_section("Powers"), "Wyrd Powers")}


@pytest.fixture
def ranks(default_pack):
    return {
        "Champion": create_subtype("Champion", id=CHAMPION_SUBTYPE),
        "Leader": create_subtype("Leader", id=LEADER_SUBTYPE),
        "Wyrd": create_subtype("Wyrd"),
    }


@pytest.fixture
def slot_type(default_pack):
    return create_slot_type("Archetype", allows_repeats=False)


@pytest.fixture
def leaders(slot_type, sets, skills, ranks):
    """The five archetypes as they stand today: one pickable each,
    carrying the gang's reading and the Champion's at once."""
    made = {}
    for name, pk in ARCHETYPES:
        pickable = create_pickable(name, slot_type, qualifier="Archetype", id=pk)
        modifier(
            f"{name}: Leader models — Savant is Primary",
            targets_every_model(has_subtypes(ranks["Leader"])),
            ef_places(sets["Savant"], skills["primary"]),
            attach_to=pickable,
        )
        modifier(
            f"{name}: Hive Scum — Cunning is Secondary",
            targets_every_model(),
            ef_places(sets["Cunning"], skills["secondary"]),
            attach_to=pickable,
        )
        modifier(
            f"{name}: Champion (own pick) — Combat is Primary",
            targets_model(has_subtypes(ranks["Champion"])),
            ef_places(sets["Combat"], skills["primary"]),
            attach_to=pickable,
        )
        made[name] = pickable
    return made


@pytest.fixture
def wyrd(leaders, ranks, sets, skills):
    """Wyrd's three extra modifiers — the ones the bearer rule does not
    sort on its own."""
    from n26.library.models import Power

    pickable = leaders["Wyrd"]
    modifier(
        "Wyrd, Champion models: adds Wyrd",
        targets_every_model(has_subtypes(ranks["Champion"])),
        ef_adds(ranks["Wyrd"]),
        attach_to=pickable,
        id=WYRD_ADDS_TO_CHAMPIONS,
    )
    modifier(
        "Wyrd, Champion or Leader models: offers a choice of power from Primary",
        targets_model(has_subtypes(ranks["Champion"], ranks["Leader"])),
        ef_offers_choice(Power, from_section=skills["primary"]),
        attach_to=pickable,
        id=WYRD_OFFERS_A_POWER,
    )
    modifier(
        "Wyrd: puts Wyrd Powers under Primary",
        targets_every_model(),
        ef_places(sets["Wyrd Powers"], skills["primary"]),
        attach_to=pickable,
        id=WYRD_POWERS_ARE_PRIMARY,
    )
    return pickable


@pytest.fixture
def outcast(slot_type, leaders, wyrd):
    """Both slots, drawing from the one picklist."""
    picklist = create_picklist(
        "Archetypes", slot_type, members=[leaders[name] for name, _ in ARCHETYPES]
    )
    create_slot(
        "Archetype",
        slot_type,
        picklist,
        label="Archetype",
        assigned_to="gang",
        id=GANG_SLOT,
    )
    return create_slot(
        "Archetype (Champion)",
        slot_type,
        picklist,
        label="Archetype",
        min_picks=0,
        assigned_to="bearer",
        id=CHAMPION_SLOT,
    )


def champion(name):
    return Pickable.objects.get(name=name, qualifier=QUALIFIER)


def scope_of(pk):
    return Modifier.objects.get(pk=pk).targets_miniature


def named_by(pk):
    """The subtypes the one condition on this modifier's scope names,
    and whether it is read the other way round."""
    (row,) = scope_of(pk).has_subtypes.all()
    return sorted(s.name for s in row.subtypes.all()), row.negate


class TestABlankLibrary:
    """Nothing to find is a normal outcome, not a failure: a fresh
    database migrates before any content is loaded into it."""

    def test_it_changes_nothing_and_says_so(self, db):
        report = make_champion_archetypes(apps)

        assert report == [
            "nothing to split — this library holds no Champion Archetype slot"
        ]
        assert not Pickable.objects.exists()

    def test_a_slot_without_its_archetypes_changes_nothing(
        self, slot_type, default_pack
    ):
        create_slot(
            "Archetype (Champion)",
            slot_type,
            create_picklist("Archetypes", slot_type),
            assigned_to="bearer",
            id=CHAMPION_SLOT,
        )

        report = make_champion_archetypes(apps)

        assert report == ["nothing to split — this library holds no Brawler archetype"]
        assert not Picklist.objects.filter(name=PICKLIST).exists()


class TestTheChampionsOwnArchetypes:
    def test_each_archetype_gains_a_copy_under_the_same_name(self, outcast):
        make_champion_archetypes(apps)

        for name, _ in ARCHETYPES:
            copy = champion(name)
            assert str(copy) == name
            assert copy.authoring_label == f"{name} — {QUALIFIER}"
            assert copy.slot_type_id == outcast.slot_type_id

    def test_they_sit_on_a_list_of_their_own_in_the_printed_order(self, outcast):
        make_champion_archetypes(apps)

        picklist = Picklist.objects.get(name=PICKLIST)
        assert [member.pickable.name for member in picklist.members.all()] == [
            name for name, _ in ARCHETYPES
        ]

    def test_the_champions_slot_draws_from_that_list(self, outcast):
        make_champion_archetypes(apps)

        outcast.refresh_from_db()
        assert outcast.picklist.name == PICKLIST

    def test_the_gangs_slot_still_draws_from_the_old_one(self, outcast):
        make_champion_archetypes(apps)

        assert Slot.objects.get(pk=GANG_SLOT).picklist.name == "Archetypes"


class TestWhichModifiersMoved:
    """A modifier reaching only the model carrying it does nothing at all
    on a pick the gang holds, so it was the Champion's all along."""

    def test_the_champions_own_reading_moves_across(self, outcast, leaders):
        make_champion_archetypes(apps)

        for name, _ in ARCHETYPES:
            moved = [m.name for m in champion(name).modifiers.all()]
            assert f"{name}: Champion (own pick) — Combat is Primary" in moved

    def test_the_gangs_reading_stays_where_it_was(self, outcast, leaders):
        make_champion_archetypes(apps)

        for name, _ in ARCHETYPES:
            kept = [m.name for m in leaders[name].modifiers.all()]
            assert f"{name}: Leader models — Savant is Primary" in kept
            assert f"{name}: Hive Scum — Cunning is Secondary" in kept
            assert f"{name}: Champion (own pick) — Combat is Primary" not in kept

    def test_the_rows_themselves_are_reused(self, outcast, leaders):
        before = Modifier.objects.count()

        make_champion_archetypes(apps)

        # Two new modifiers, both Wyrd's: the Leader's own offer and the
        # Champion's own Wyrd Powers placement.
        assert Modifier.objects.count() == before + 2


class TestWyrd:
    def test_the_subtype_grant_becomes_the_champions_own(self, outcast, wyrd):
        make_champion_archetypes(apps)

        assert scope_of(WYRD_ADDS_TO_CHAMPIONS).reach == "bearer"
        assert champion("Wyrd").modifiers.filter(pk=WYRD_ADDS_TO_CHAMPIONS).exists()
        assert not wyrd.modifiers.filter(pk=WYRD_ADDS_TO_CHAMPIONS).exists()

    def test_the_power_offer_ends_up_on_both_pickables(self, outcast, wyrd):
        make_champion_archetypes(apps)

        assert champion("Wyrd").modifiers.filter(pk=WYRD_OFFERS_A_POWER).exists()
        assert named_by(WYRD_OFFERS_A_POWER) == (["Champion"], False)

        theirs = wyrd.modifiers.get(name=LEADER_OFFER)
        assert theirs.targets_miniature.reach == "every_model"
        assert named_by(theirs.pk) == (["Leader"], False)
        assert (
            theirs.offers_choice.from_section_id
            == Modifier.objects.get(
                pk=WYRD_OFFERS_A_POWER
            ).offers_choice.from_section_id
        )

    def test_the_gangs_wyrd_powers_placement_skips_champions(self, outcast, wyrd):
        make_champion_archetypes(apps)

        assert wyrd.modifiers.filter(pk=WYRD_POWERS_ARE_PRIMARY).exists()
        assert named_by(WYRD_POWERS_ARE_PRIMARY) == (["Champion"], True)

    def test_the_champions_wyrd_places_the_powers_for_itself(self, outcast, wyrd):
        make_champion_archetypes(apps)

        own = champion("Wyrd").modifiers.get(name=CHAMPION_WYRD_POWERS)
        assert own.targets_miniature.reach == "bearer"
        assert not own.targets_miniature.has_subtypes.exists()
        source = Modifier.objects.get(pk=WYRD_POWERS_ARE_PRIMARY).places_category
        assert own.places_category.category_id == source.category_id
        assert own.places_category.section_id == source.section_id


class TestRunningItAgain:
    def test_a_second_pass_finds_the_split_already_made(self, outcast):
        make_champion_archetypes(apps)
        counts = (Pickable.objects.count(), Modifier.objects.count())

        report = make_champion_archetypes(apps)

        assert report == [
            "nothing to split — the Champion archetypes are already there"
        ]
        assert (Pickable.objects.count(), Modifier.objects.count()) == counts
