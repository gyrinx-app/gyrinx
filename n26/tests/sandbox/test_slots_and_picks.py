"""Slots identify authored choices; picks record their selected content.

Build a slot type, pickables, a picklist and a slot through authoring verbs.
The Gang Legacy fixtures offer three houses with their equipment collections.

Assigning a slot exposes a computed choice. Picks identify their granting
assignment through chosen_for and, when needed, their slot. Unanchored
pickables neither apply modifiers nor satisfy pick conditions. Removing a
granting pick retracts dependent choices and selections. See test_choosing.py
for the picker workflow.
"""

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User

from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.models import Assignment
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.core.render import (
    _provenance_within,
    build_choice_offer,
    build_model_card,
    render_gang,
)
from n26.library.authoring import targets_model as targets_model_with
from n26.library.models import Pickable, Slot
from n26.tests.fixtures import library_setup
from n26.tests.sandbox.actions import (
    add_built_in,
    add_picklist_member,
    assign,
    buy,
    changes_stat,
    choose,
    create_affiliation,
    create_collection,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
    create_subtype,
    create_wargear,
    ef_adds,
    found_gang,
    has_pickable,
    has_subtypes,
    hire,
    modifier,
    refund,
    remove,
    targets_every_model,
    targets_gang,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def legacy(default_pack):
    """Create a Gang Legacy slot type that does not allow repeats."""
    return create_slot_type(
        "Gang Legacy", plural_name="Gang Legacies", allows_repeats=False
    )


@pytest.fixture
@library_setup
def houses(legacy):
    """Create three house picks, each granting its own equipment collection."""
    made = {}
    for name in ("Cawdor", "Escher", "Ironhead Squats"):
        pickable = create_pickable(name, legacy)
        modifier(
            f"{name}: its equipment list",
            targets_model(),
            ef_adds(create_collection(f"House {name} Equipment List")),
            carried_by=pickable,
        )
        made[name] = pickable
    return made


@pytest.fixture
def legacies(legacy, houses):
    return create_picklist("Gang Legacies", legacy, members=list(houses.values()))


@pytest.fixture
def gang_legacy_slot(legacy, legacies):
    return create_slot("Gang Legacy", legacy, legacies)


@pytest.fixture
@library_setup
def hunter(person_type, gang_type, gang_legacy_slot):
    """Build an unresolved Gang Legacy slot into the profile."""
    profile = create_profile("Hunter", person_type, gang_type, price=100)
    add_built_in(profile, gang_legacy_slot)
    return profile


@pytest.fixture
@library_setup
def squats_hunter(person_type, gang_type, gang_legacy_slot, houses):
    """Build a Gang Legacy slot into the profile with an initial Squats pick."""
    profile = create_profile("Squats Hunter", person_type, gang_type, price=100)
    add_built_in(profile, gang_legacy_slot, default_pickable=houses["Ironhead Squats"])
    return profile


@pytest.fixture
def gang(owner, gang_type):
    return found_gang("The Long Hunt", gang_type, owner=owner, budget=1000)


def card_of(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return card, compute(card, index)


def choices_of(miniature):
    _, computed = card_of(miniature)
    return computed.choices


def drawn_card(miniature):
    card, computed = card_of(miniature)
    return build_model_card(miniature, card=card, computed=computed)


def gang_choices(gang):
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute_gang(card, index)


class TestMakingTheChoice:
    """Compute an unresolved choice from its assigned slot without writing pending picks or spending credits."""

    def test_a_free_pick_settles_the_row_and_gives_its_payload_without_changing_rating(
        self, gang, hunter, houses
    ):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (slot,) = choices_of(kaustos)
        assert slot.kind_label == "Gang Legacy"
        assert not slot.is_resolved
        assert (slot.min_picks, slot.max_picks) == (1, 1)
        assert_reconciled(gang)

        drawn = drawn_card(kaustos)
        assert [line.name for line in drawn.equipment] == []
        assert [line.kind_label for line in drawn.choices] == ["Gang Legacy"]
        assert [note.text for note in drawn.remarks] == ["Gang Legacy — 0 of 1 chosen"]
        assert_reconciled(gang)

        assert not next(iter(drawn_card(kaustos).choices)).is_full
        (open_slot,) = choices_of(kaustos)
        before = gang.rating
        choose(open_slot.anchor.assignment, houses["Cawdor"])

        _, computed = card_of(kaustos)
        (settled,) = computed.choices
        assert settled.chosen_name == "Cawdor"
        assert [line.name for line in computed.collections] == [
            "House Cawdor Equipment List"
        ]
        drawn = drawn_card(kaustos)
        assert [line.name for line in drawn.equipment] == []
        assert [line.chosen for line in drawn.choices] == ["Cawdor"]
        assert drawn.remarks == []
        gang.refresh_from_db()
        assert gang.rating == before
        assert_reconciled(gang)

        sheet = render_gang(gang)

        (drawn,) = sheet.models
        assert [line.chosen for line in drawn.choices] == ["Cawdor"]
        assert_reconciled(gang)

        line = next(iter(drawn_card(kaustos).choices))
        assert line.is_resolved and line.is_full

    def test_a_pick_from_another_slot_type_settles_nothing_and_is_refused(
        self, gang, hunter, default_pack
    ):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (open_slot,) = choices_of(kaustos)
        elsewhere = create_pickable("Aranthian", create_slot_type("Affiliation"))

        with pytest.raises(Refusal, match="Aranthian cannot be a pick for Gang Legacy"):
            choose(open_slot.anchor.assignment, elsewhere)

    def test_a_pickable_the_list_does_not_offer_is_still_the_owners_to_give(
        self, gang, hunter, legacy
    ):
        """Allow a direct operation to select an off-list pickable of the matching slot type."""
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (open_slot,) = choices_of(kaustos)
        unlisted = create_pickable("Delaque", legacy)

        choose(open_slot.anchor.assignment, unlisted)

        (settled,) = choices_of(kaustos)
        assert settled.chosen_name == "Delaque"


class TestASlotWithADefault:
    """Hired from a profile carrying the pick, the choice arrives made."""

    def test_a_default_names_its_source_then_removal_and_rechoice_keep_the_slot(
        self, gang, squats_hunter, houses
    ):
        grendel = hire(gang, squats_hunter, "Grendel", paid=100)
        (settled,) = choices_of(grendel)
        assert settled.chosen_name == "Ironhead Squats"
        assert_reconciled(gang)

        card, computed = card_of(grendel)
        (settled,) = computed.choices
        provenance = _provenance_within(card, computed=computed)(settled.picks[0])
        assert settled.offer is None
        assert not provenance.chosen
        assert provenance.description == "From Gang Legacy"
        assert_reconciled(gang)

        slot = Assignment.objects.get(slot__isnull=False, miniature_root=grendel)
        pick = Assignment.objects.get(pickable__isnull=False, miniature_root=grendel)
        assert pick.chosen_for == slot
        assert pick.caused_by == slot

        remove(settled.picks[0].assignment)
        (still_asked,) = choices_of(grendel)
        assert not still_asked.is_resolved
        choose(still_asked.anchor.assignment, houses["Escher"])

        (line,) = drawn_card(grendel).choices
        assert line.kind_label == "Gang Legacy"
        assert line.chosen == "Escher"
        assert line.provenance.source == "Gang Legacy"
        assert not line.provenance.chosen
        assert_reconciled(gang)
        (rechosen,) = choices_of(grendel)
        assert rechosen.chosen_name == "Escher"
        assert_reconciled(gang)


class TestTwoChoicesOfOneSlotType:
    """Keep two slots of the same type independent by recording which assignment each pick answers."""

    @pytest.fixture
    @library_setup
    def twice_asked(self, person_type, gang_type, legacy, legacies):
        first = create_slot("Legacy 1", legacy, legacies, label="First legacy")
        second = create_slot("Legacy 2", legacy, legacies, label="Second legacy")
        profile = create_profile("Twice-born", person_type, gang_type, price=100)
        add_built_in(profile, first)
        add_built_in(profile, second)
        return profile

    def test_each_holds_its_own_answer(self, gang, twice_asked, houses):
        kaustos = hire(gang, twice_asked, "Kaustos", paid=100)
        first, second = sorted(choices_of(kaustos), key=lambda s: s.kind_label)

        choose(first.anchor.assignment, houses["Cawdor"])

        first, second = sorted(choices_of(kaustos), key=lambda s: s.kind_label)
        assert first.chosen_name == "Cawdor"
        assert second.chosen_name is None

        choose(second.anchor.assignment, houses["Cawdor"])

        drawn = drawn_card(kaustos)

        assert "Cawdor is chosen for both Legacy 1 and Legacy 2" in [
            note.text for note in drawn.remarks
        ]

    def test_a_slot_type_that_allows_repeats_says_nothing(
        self, gang, person_type, gang_type, default_pack
    ):
        slot_type = create_slot_type("Loadout", allows_repeats=True)
        pickable = create_pickable("Heavy", slot_type)
        picklist = create_picklist("Loadouts", slot_type, members=[pickable])
        profile = create_profile("Twice-armed", person_type, gang_type, price=100)
        add_built_in(profile, create_slot("Loadout 1", slot_type, picklist))
        add_built_in(profile, create_slot("Loadout 2", slot_type, picklist))

        kaustos = hire(gang, profile, "Kaustos", paid=100)
        for slot in choices_of(kaustos):
            choose(slot.anchor.assignment, pickable)

        drawn = drawn_card(kaustos)
        assert [note.text for note in drawn.remarks] == []


class TestThePickerMarksWhatIsTaken:
    """Mark picks selected for another slot of a non-repeating type without disabling them.

    Duplicate selection produces a card note rather than blocking the choice.
    """

    @pytest.fixture
    @library_setup
    def twice_asked(self, person_type, gang_type, legacy, legacies):
        profile = create_profile("Twice-born", person_type, gang_type, price=100)
        add_built_in(profile, create_slot("Legacy 1", legacy, legacies))
        add_built_in(profile, create_slot("Legacy 2", legacy, legacies))
        return profile

    def offers(self, miniature):
        """Build both choice offers in source-name order."""
        from n26.core.render import build_choice_offer

        _, computed = card_of(miniature)
        return [
            build_choice_offer(slot, computed)
            for slot in sorted(computed.choices, key=lambda slot: slot.source)
        ]

    def marks(self, offer):
        return {
            pickable.name: pickable.taken_for
            for group in offer.groups
            for pickable in group.options
        }

    def test_the_pickable_the_other_choice_holds_is_marked(
        self, gang, twice_asked, houses, client, owner
    ):
        import re

        from n26.core.views.choose import link_slots

        kaustos = hire(gang, twice_asked, "Kaustos", paid=100)
        first, _ = sorted(choices_of(kaustos), key=lambda slot: slot.source)
        choose(first.anchor.assignment, houses["Cawdor"])

        _, second = self.offers(kaustos)

        assert self.marks(second) == {
            "Cawdor": "Legacy 1",
            "Escher": "",
            "Ironhead Squats": "",
        }

        here, _ = self.offers(kaustos)
        (cawdor,) = [
            pickable
            for group in here.groups
            for pickable in group.options
            if pickable.name == "Cawdor"
        ]

        assert (cawdor.taken_for, cawdor.is_current) == ("", True)

        client.force_login(owner)

        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        (card,) = sheet.models
        second = sorted(card.questions, key=lambda line: line.kind_label)[1]
        body = client.get(second.href).content.decode()

        assert "already chosen for Legacy 1" in body
        # Keep the marked pick selectable.
        control = re.search(
            rf'<input[^>]*value="library.pickable:{houses["Cawdor"].pk}"[^>]*>', body
        )
        assert control and "disabled" not in control.group()

    def test_a_slot_type_that_allows_repeats_marks_nothing(
        self, gang, person_type, gang_type, default_pack
    ):
        slot_type = create_slot_type("Loadout", allows_repeats=True)
        pickable = create_pickable("Heavy", slot_type)
        picklist = create_picklist("Loadouts", slot_type, members=[pickable])
        profile = create_profile("Twice-armed", person_type, gang_type, price=100)
        add_built_in(profile, create_slot("Loadout 1", slot_type, picklist))
        add_built_in(profile, create_slot("Loadout 2", slot_type, picklist))
        kaustos = hire(gang, profile, "Kaustos", paid=100)
        first, _ = sorted(choices_of(kaustos), key=lambda slot: slot.source)
        choose(first.anchor.assignment, pickable)

        _, second = self.offers(kaustos)

        assert self.marks(second) == {"Heavy": ""}


class TestAnPickableWithNoChoiceBehindIt:
    """Ignore pickables assigned without a choice: hide their lines, skip their modifiers and exclude them from pick conditions."""

    @pytest.fixture
    @library_setup
    def loud(self, legacy, default_pack):
        """Create a pickable granting a distinctive rule so unintended modifier execution is visible."""
        pickable = create_pickable("Cawdor", legacy)
        modifier(
            "Cawdor: a rule",
            targets_model(),
            ef_adds(create_rule("House Cawdor")),
            carried_by=pickable,
        )
        return pickable

    @pytest.fixture
    @library_setup
    def plain_hunter(self, person_type, gang_type):
        return create_profile("Hunter", person_type, gang_type, price=100)

    def test_its_modifiers_do_not_run(self, gang, plain_hunter, loud):
        kaustos = hire(gang, plain_hunter, "Kaustos", paid=100)
        assign(loud, miniature=kaustos)

        _, computed = card_of(kaustos)

        assert [line.name for line in computed.rules] == []

        drawn = drawn_card(kaustos)

        assert [line.name for line in drawn.equipment] == []
        assert drawn.choices == []

    def test_no_rule_can_match_on_it(self, gang, plain_hunter, loud, default_pack):
        """Exclude an unanchored pickable from has_pickable conditions."""
        marker = create_rule("Noticed")
        gear = create_wargear("Watcher")
        modifier(
            "Watcher: notices Cawdor",
            targets_model_with(has_pickable(loud)),
            ef_adds(marker),
            carried_by=gear,
        )
        kaustos = hire(gang, plain_hunter, "Kaustos", paid=100)
        assign(loud, miniature=kaustos)
        assign(gear, miniature=kaustos)

        _, computed = card_of(kaustos)

        assert [line.name for line in computed.rules] == []

    def test_the_same_pickable_chosen_properly_does_everything(
        self, gang, hunter, legacy
    ):
        loud = create_pickable("Delaque", legacy)
        modifier(
            "Delaque: a rule",
            targets_model(),
            ef_adds(create_rule("House Delaque")),
            carried_by=loud,
        )
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (open_slot,) = choices_of(kaustos)

        choose(open_slot.anchor.assignment, loud)

        _, computed = card_of(kaustos)
        assert [line.name for line in computed.rules] == ["House Delaque"]


class TestAHiddenChoice:
    """Hide the choice row and selected pick while applying its effects."""

    @pytest.fixture
    @library_setup
    def bundled(self, person_type, gang_type, legacy, legacies, houses, default_pack):
        slot = create_slot("Hidden legacy", legacy, legacies, hidden=True)
        profile = create_profile("Bundled", person_type, gang_type, price=100)
        add_built_in(profile, slot, default_pickable=houses["Cawdor"])
        return profile

    def test_a_hand_made_pick_draws_no_line_either(
        self, gang, bundled, houses, legacy, legacies
    ):
        """Apply manually chosen hidden picks without drawing the choice or pick as separate lines."""
        from n26.core.models import Assignment
        from n26.library.models import Slot

        kaustos = hire(gang, bundled, "Kaustos", paid=100)
        assert choices_of(kaustos) == []
        assert drawn_card(kaustos).choices == []

        _, computed = card_of(kaustos)

        assert [line.name for line in computed.collections] == [
            "House Cawdor Equipment List"
        ]

        drawn = drawn_card(kaustos)

        assert drawn.remarks == []

        slot = Slot.objects.get(name="Hidden legacy")
        standing = Assignment.objects.get(
            miniature_root=kaustos, pickable__isnull=False, archived=False
        )
        remove(standing)
        choose(
            Assignment.objects.get(profile=bundled, miniature_root=kaustos),
            houses["Escher"],
            slot=slot,
            miniature=kaustos,
        )

        drawn = drawn_card(kaustos)
        assert drawn.choices == []
        assert not any(
            "Escher" in str(getattr(drawn, field))
            for field in ("equipment", "rules", "skills", "subtypes")
        )
        _, computed = card_of(kaustos)
        assert [line.name for line in computed.collections] == [
            "House Escher Equipment List"
        ]


class TestAChoiceTheGangIsAsked:
    """Ask a gang-hosted choice once on the gang card while broadcasting its selected content to members."""

    @pytest.fixture
    @library_setup
    def gang_type_with_affiliation(self, default_pack):
        slot_type = create_slot_type("Affiliation")
        aranthian = create_pickable("Aranthian", slot_type)
        picklist = create_picklist("Affiliations", slot_type, members=[aranthian])
        slot = create_slot(
            "Affiliation", slot_type, picklist, assigned_to="gang", min_picks=1
        )
        made = create_gang_type("Outcasts")
        add_built_in(made, slot)
        return made, aranthian

    def test_no_members_card_asks_it_again(
        self, owner, gang_type_with_affiliation, person_type
    ):
        made, _ = gang_type_with_affiliation
        gang = found_gang("The Outcasts", made, owner=owner, budget=1000)
        profile = create_profile("Outcast", person_type, made, price=50)
        kaustos = hire(gang, profile, "Kaustos", paid=50)

        assert choices_of(kaustos) == []
        assert_reconciled(gang)

    def test_the_pick_lands_on_the_gang(self, owner, gang_type_with_affiliation):
        made, aranthian = gang_type_with_affiliation
        gang = found_gang("The Outcasts", made, owner=owner, budget=1000)
        (slot,) = gang_choices(gang).choices

        assert slot.kind_label == "Affiliation"
        assert not slot.is_resolved

        assert "Affiliation — 0 of 1 chosen" in [
            note.text for note in gang_choices(gang).notes
        ]

        choose(slot.anchor.assignment, aranthian)

        written = Assignment.objects.get(pickable=aranthian)
        assert written.gang == gang
        assert gang_choices(gang).choices[0].chosen_name == "Aranthian"


class TestALeaderAskedForTheGang:
    """Offer a choice on the Leader and store its selected pick on the gang.

    The gang-hosted pick broadcasts to member cards, where its authored rank
    conditions determine which models receive its effects.
    """

    @pytest.fixture
    @library_setup
    def ranks(self, default_pack):
        return {
            name.lower(): create_subtype(name)
            for name in ("Ganger", "Hive Scum", "Champion")
        }

    @pytest.fixture
    @library_setup
    def leader(self, person_type, gang_type, ranks, default_pack):
        slot_type = create_slot_type("Archetype", allows_repeats=False)
        mutant = create_pickable("Mutant", slot_type)
        modifier(
            "Mutant: the gangers and the scum",
            targets_every_model(has_subtypes(ranks["ganger"], ranks["hive scum"])),
            ef_adds(create_rule("Unstable")),
            carried_by=mutant,
        )
        picklist = create_picklist("Outcast Archetypes", slot_type, members=[mutant])
        slot = create_slot("Archetype", slot_type, picklist, assigned_to="gang")
        profile = create_profile("Outcast Leader", person_type, gang_type, price=120)
        add_built_in(profile, slot)
        return profile, mutant

    def test_what_he_picks_is_the_gangs(self, gang, leader):
        profile, mutant = leader
        boss = hire(gang, profile, "Boss", paid=120)
        (slot,) = choices_of(boss)

        assert slot.kind_label == "Archetype"

        choose(slot.anchor.assignment, mutant)

        assert Assignment.objects.get(pickable=mutant).gang == gang
        assert_reconciled(gang)

    def test_the_payload_reaches_the_ranks_it_names(
        self, gang, leader, ranks, person_type, gang_type
    ):
        profile, mutant = leader
        entries = {}
        for key, name, price in [
            ("ganger", "Ganger", 50),
            ("hive scum", "Hive Scum", 20),
            ("champion", "Champion", 80),
        ]:
            entry = create_profile(name, person_type, gang_type, price=price)
            add_built_in(entry, ranks[key])
            entries[key] = entry

        boss = hire(gang, profile, "Boss", paid=120)
        crew = {
            key: hire(gang, entry, key.title(), paid=entry.price)
            for key, entry in entries.items()
        }
        (slot,) = choices_of(boss)
        choose(slot.anchor.assignment, mutant)

        reached = {
            key: [line.name for line in card_of(model)[1].rules]
            for key, model in crew.items()
        }
        assert reached == {
            "ganger": ["Unstable"],
            "hive scum": ["Unstable"],
            "champion": [],
        }
        assert_reconciled(gang)


class TestOneChoiceOpensAnother:
    """Anchor a follow-up choice and its pick to the granting pick so removal retracts the chain."""

    @pytest.fixture
    @library_setup
    def chained(self, person_type, gang_type, default_pack):
        slot_type = create_slot_type("Affiliation")
        houses_slot_type = create_slot_type("House")
        cawdor = create_pickable("House Cawdor", houses_slot_type)
        house_list = create_picklist("Clan Houses", houses_slot_type, members=[cawdor])
        house_slot = create_slot("House", houses_slot_type, house_list)

        clan_house = create_pickable("Clan House", slot_type)
        modifier(
            "Clan House: which house",
            targets_model(),
            ef_adds(house_slot),
            carried_by=clan_house,
        )
        affiliations = create_picklist("Affiliations", slot_type, members=[clan_house])
        first = create_slot("Affiliation", slot_type, affiliations)
        profile = create_profile("Outcast", person_type, gang_type, price=100)
        add_built_in(profile, first)
        return profile, clan_house, cawdor

    def test_the_second_is_answered_against_what_gave_it(self, gang, chained):
        profile, clan_house, cawdor = chained
        kaustos = hire(gang, profile, "Kaustos", paid=100)
        (first,) = choices_of(kaustos)
        choose(first.anchor.assignment, clan_house)
        assert sorted(slot.kind_label for slot in choices_of(kaustos)) == [
            "Affiliation",
            "House",
        ]

        second = next(s for s in choices_of(kaustos) if s.kind_label == "House")

        choose(second.anchor.assignment, cawdor, slot=second.slot)

        second = next(s for s in choices_of(kaustos) if s.kind_label == "House")
        assert second.chosen_name == "House Cawdor"

        remove(Assignment.objects.get(pickable=clan_house, archived=False))

        assert [slot.kind_label for slot in choices_of(kaustos)] == ["Affiliation"]
        assert not Assignment.objects.filter(pickable=cawdor, archived=False).exists()
        assert_reconciled(gang)


class TestAGangPickOpensAChoiceOnEveryModel:
    """A gang pick grants a separate model-targeted choice to each fighter.

    Anchor each selection to the gang pick and its recipient model. The gang
    card has no model target, so it does not receive the follow-up choice.
    """

    @pytest.fixture
    @library_setup
    def guild_shape(self, person_type, gang_type, default_pack):
        alliance = create_slot_type("Alliance")
        role = create_slot_type("Guild Role")
        nauticus = create_pickable("Nauticus", role)
        modifier(
            "Nauticus: its rule",
            targets_model_with(),
            ef_adds(create_rule("Master of Water")),
            carried_by=nauticus,
        )
        roles = create_picklist("Guild Roles", role, members=[nauticus])
        role_slot = create_slot("Guild Role", role, roles)
        guild = create_pickable("Water Guild", alliance)
        modifier(
            "Water Guild grants the Guild Role choice",
            targets_every_model(),
            ef_adds(role_slot),
            carried_by=guild,
        )
        guilds = create_picklist("Guilds", alliance, members=[guild])
        alliance_slot = create_slot("Alliance", alliance, guilds, assigned_to="gang")
        add_built_in(gang_type, alliance_slot)
        profile = create_profile("Hunter", person_type, gang_type, price=100)
        return profile, guild, nauticus, role_slot

    @pytest.fixture
    def gang(self, owner, gang_type, guild_shape):
        # Create the built-in slot before founding so the gang receives its assignment.
        return found_gang("The Long Hunt", gang_type, owner=owner, budget=1000)

    def crew_with_the_pick(self, gang, profile, guild):
        fighters = [
            hire(gang, profile, name, paid=100) for name in ("Kaustos", "Grendel")
        ]
        (alliance_row,) = gang_choices(gang).choices
        choose(alliance_row.anchor.assignment, guild)
        return fighters

    def test_the_role_settles_per_fighter_and_its_payload_lands(
        self, gang, guild_shape
    ):
        profile, guild, nauticus, role_slot = guild_shape
        kaustos, grendel = self.crew_with_the_pick(gang, profile, guild)
        for fighter in (kaustos, grendel):
            assert [row.kind_label for row in choices_of(fighter)] == ["Guild Role"]
        assert [row.kind_label for row in gang_choices(gang).choices] == ["Alliance"]
        assert_reconciled(gang)
        (role_row,) = choices_of(kaustos)

        choose(role_row.anchor.assignment, nauticus, slot=role_slot, miniature=kaustos)

        _, computed = card_of(kaustos)
        assert [line.name for line in computed.rules] == ["Master of Water"]
        assert card_of(grendel)[1].rules == []
        assert Assignment.objects.get(pickable=nauticus).miniature == kaustos
        assert_reconciled(gang)

        remove(Assignment.objects.get(pickable=guild))

        assert choices_of(kaustos) == []
        assert not Assignment.objects.filter(
            pickable__isnull=False, archived=False
        ).exists()
        assert_reconciled(gang)

    def test_each_fighter_settles_their_own_independently(self, gang, guild_shape):
        profile, guild, nauticus, role_slot = guild_shape
        kaustos, grendel = self.crew_with_the_pick(gang, profile, guild)

        for fighter in (kaustos, grendel):
            (role_row,) = choices_of(fighter)
            choose(
                role_row.anchor.assignment, nauticus, slot=role_slot, miniature=fighter
            )

        assert sorted(
            Assignment.objects.filter(pickable=nauticus).values_list(
                "miniature__name", flat=True
            )
        ) == ["Grendel", "Kaustos"]
        for fighter in (kaustos, grendel):
            assert [line.name for line in card_of(fighter)[1].rules] == [
                "Master of Water"
            ]
        assert_reconciled(gang)

    def test_the_screen_asks_on_the_fighters_card_and_the_click_lands(
        self, gang, guild_shape, client, owner
    ):
        from n26.core.views.choose import link_slots

        profile, guild, nauticus, _ = guild_shape
        kaustos, _ = self.crew_with_the_pick(gang, profile, guild)
        client.force_login(owner)
        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        card = next(drawn for drawn in sheet.models if drawn.name == "Kaustos")
        (line,) = card.questions

        body = client.get(line.href).content.decode()
        assert "Nauticus" in body
        response = client.post(line.href, {"thing": f"library.pickable:{nauticus.pk}"})

        assert response.status_code == 302
        assert Assignment.objects.get(pickable=nauticus).miniature == kaustos
        assert_reconciled(gang)


class TestAChoiceOpenedFurtherDownTheChain:
    """Anchor a choice granted through computed hidden content to the stored equipment supporting the grant chain."""

    @pytest.fixture
    @library_setup
    def relic(self, person_type, gang_type, default_pack):
        rite = create_slot_type("Rite")
        vigil = create_pickable("The Vigil", rite)
        modifier(
            "The Vigil: its rule",
            targets_model_with(),
            ef_adds(create_rule("Keeps the Vigil")),
            carried_by=vigil,
        )
        rites = create_picklist("Rites", rite, members=[vigil])
        rite_slot = create_slot("Rite", rite, rites)
        observances = create_hidden("The relic's observances")
        modifier(
            "The observances open the Rite choice",
            targets_model(),
            ef_adds(rite_slot),
            carried_by=observances,
        )
        relic = create_wargear("Reliquary", price=30)
        modifier(
            "Reliquary: it carries its observances",
            targets_model(),
            ef_adds(observances),
            carried_by=relic,
        )
        profile = create_profile("Devotee", person_type, gang_type, price=100)
        return profile, relic, vigil, rite_slot

    def test_what_is_picked_lands_and_giving_the_wargear_back_takes_it(
        self, gang, relic
    ):
        profile, wargear, vigil, rite_slot = relic
        kaustos = hire(gang, profile, "Kaustos", paid=100)
        bought = buy(kaustos, thing=wargear, paid=30)
        (rite_row,) = choices_of(kaustos)
        assert rite_row.kind_label == "Rite"
        assert rite_row.anchor.assignment == bought
        assert_reconciled(gang)
        choose(rite_row.anchor.assignment, vigil, slot=rite_slot)
        assert [line.name for line in card_of(kaustos)[1].rules] == ["Keeps the Vigil"]

        refund(bought)

        assert choices_of(kaustos) == []
        assert not Assignment.objects.filter(pickable=vigil, archived=False).exists()
        # Refresh this instance after the refund updated the gang through its assignment.
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestAGangGuestOpensAChoiceOnEveryModel:
    """A rule computed on the gang grants a separate choice to each fighter.

    Echo the computed rule onto member cards and anchor their choices to the
    stored alliance supporting the grant chain. No rule assignment is created.
    """

    @pytest.fixture
    @library_setup
    def guild_shape(self, person_type, gang_type, default_pack):
        role = create_slot_type("Guild Role")
        nauticus = create_pickable("Nauticus", role)
        modifier(
            "Nauticus: its rule",
            targets_model_with(),
            ef_adds(create_rule("Master of Water")),
            carried_by=nauticus,
        )
        roles = create_picklist("Guild Roles", role, members=[nauticus])
        role_slot = create_slot("Guild Role", role, roles)
        # The alliance grants the rule in memory, and that rule grants the member choice.
        pact = create_rule("The Water Pact")
        modifier(
            "The Water Pact: every hand has a role",
            targets_every_model(),
            ef_adds(role_slot),
            carried_by=pact,
        )
        alliance = create_affiliation("Water Guild")
        modifier(
            "Water Guild: the gang has the Water Pact",
            targets_gang(),
            ef_adds(pact),
            carried_by=alliance,
        )
        profile = create_profile("Hunter", person_type, gang_type, price=100)
        return profile, alliance, nauticus, role_slot

    @pytest.fixture
    def gang(self, owner, gang_type):
        return found_gang("The Long Hunt", gang_type, owner=owner, budget=1000)

    def crew_and_alliance(self, gang, profile, alliance):
        fighters = [
            hire(gang, profile, name, paid=100) for name in ("Kaustos", "Grendel")
        ]
        return fighters, assign(alliance, gang=gang)

    def test_the_role_settles_per_fighter_and_its_payload_lands(
        self, gang, guild_shape
    ):
        profile, alliance, nauticus, role_slot = guild_shape
        (kaustos, grendel), signed = self.crew_and_alliance(gang, profile, alliance)
        _, computed = card_of(kaustos)
        assert [guest.name for guest in computed.echoed] == ["The Water Pact"]
        assert not Assignment.objects.filter(
            rule__isnull=False, gang_root=gang
        ).exists()
        assert_reconciled(gang)

        for fighter in (kaustos, grendel):
            assert [row.kind_label for row in choices_of(fighter)] == ["Guild Role"]
        assert [row.kind_label for row in gang_choices(gang).choices] == []
        assert_reconciled(gang)
        (role_row,) = choices_of(kaustos)
        assert role_row.source == "The Water Pact"
        assert role_row.anchor.assignment == signed
        assert_reconciled(gang)

        choose(role_row.anchor.assignment, nauticus, slot=role_slot, miniature=kaustos)

        # Display the chosen model effect without drawing the echoed gang rule on the fighter card.
        assert [line.name for line in card_of(kaustos)[1].rules] == ["Master of Water"]
        assert card_of(grendel)[1].rules == []
        assert Assignment.objects.get(pickable=nauticus).miniature == kaustos
        assert_reconciled(gang)

        remove(signed)

        assert choices_of(kaustos) == []
        assert not Assignment.objects.filter(
            pickable__isnull=False, archived=False
        ).exists()
        assert_reconciled(gang)

    def test_the_screen_asks_on_the_fighters_card_and_the_click_lands(
        self, gang, guild_shape, client, owner
    ):
        from n26.core.views.choose import link_slots

        profile, alliance, nauticus, _ = guild_shape
        (kaustos, _), _ = self.crew_and_alliance(gang, profile, alliance)
        client.force_login(owner)
        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        card = next(drawn for drawn in sheet.models if drawn.name == "Kaustos")
        (line,) = card.questions

        body = client.get(line.href).content.decode()
        assert "Nauticus" in body
        response = client.post(line.href, {"thing": f"library.pickable:{nauticus.pk}"})

        assert response.status_code == 302
        assert Assignment.objects.get(pickable=nauticus).miniature == kaustos
        assert_reconciled(gang)


class TestRemovingTheChoiceItself:
    def test_the_pick_goes_with_it(self, gang, squats_hunter):
        grendel = hire(gang, squats_hunter, "Grendel", paid=100)
        slot = Assignment.objects.get(slot__isnull=False, miniature_root=grendel)

        remove(slot)

        assert choices_of(grendel) == []
        assert not Assignment.objects.filter(
            pickable__isnull=False, archived=False, miniature_root=grendel
        ).exists()
        assert_reconciled(gang)


class TestTheScreenBehindTheRow:
    """Link an assigned slot to the shared picker route and record its selection through the page."""

    def slot_line(self, gang):
        from n26.core.views.choose import link_slots

        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        (card,) = sheet.models
        (line,) = card.questions
        return line

    def test_the_click_settles_the_choice(self, gang, hunter, houses, client, owner):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        client.force_login(owner)
        href = self.slot_line(gang).href

        body = client.get(href).content.decode()
        assert "Cawdor" in body
        assert "Escher" in body
        assert kaustos.name in body
        assert 'value="none"' not in body
        said = button_labels(body)
        assert "Save" in said
        assert "Add" not in said and "Choose" not in said
        assert_reconciled(gang)

        client.post(href, {"thing": f"library.pickable:{houses['Escher'].pk}"})

        assert choices_of(kaustos)[0].chosen_name == "Escher"
        assert_reconciled(gang)

        response = client.post(href, {"thing": "none"})

        assert response.status_code == 302
        assert response.headers["Location"] == href
        (line,) = choices_of(kaustos)
        assert line.chosen_name == "Escher"

        client.post(
            self.slot_line(gang).href,
            {"thing": f"library.pickable:{houses['Cawdor'].pk}"},
        )

        (settled,) = choices_of(kaustos)
        assert settled.chosen_name == "Cawdor"
        assert len(settled.picks) == 1
        assert_reconciled(gang)


class TestAnOptionalChoiceOffersNone:
    """Offer None for optional single-pick choices to remove the current pick.

    Mandatory single-pick choices omit None. Multi-pick choices remove each
    pick through its own control instead.
    """

    @pytest.fixture
    @library_setup
    def optional_hunter(self, person_type, gang_type, legacy, legacies):
        slot = create_slot("Optional legacy", legacy, legacies, min_picks=0)
        profile = create_profile("Wanderer", person_type, gang_type, price=100)
        add_built_in(profile, slot)
        return profile

    def slot_line(self, gang):
        from n26.core.views.choose import link_slots

        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        (card,) = sheet.models
        (line,) = card.questions
        return line

    def test_clicking_none_takes_the_pick_back(
        self, gang, optional_hunter, houses, client, owner
    ):
        kaustos = hire(gang, optional_hunter, "Kaustos", paid=100)
        client.force_login(owner)
        href = self.slot_line(gang).href
        body = client.get(href).content.decode()
        assert 'value="none"' in body
        assert "None" in body

        response = client.post(self.slot_line(gang).href, {"thing": "none"})

        assert response.status_code == 302
        (line,) = choices_of(kaustos)
        assert line.chosen_name is None
        assert_reconciled(gang)

        client.post(href, {"thing": f"library.pickable:{houses['Escher'].pk}"})

        response = client.post(href, {"thing": "none"})

        assert response.status_code == 302
        (line,) = choices_of(kaustos)
        assert line.chosen_name is None
        assert not Assignment.objects.filter(
            pickable__isnull=False, archived=False
        ).exists()
        assert_reconciled(gang)

    def test_a_choice_worked_at_a_pick_at_a_time_has_no_none_row(
        self, gang, person_type, gang_type, legacy, legacies, client, owner
    ):
        """Use per-pick Remove controls rather than a None option for multi-pick choices."""
        slot = create_slot("Two legacies", legacy, legacies, min_picks=0, max_picks=2)
        profile = create_profile("Wanderer", person_type, gang_type, price=100)
        add_built_in(profile, slot)
        hire(gang, profile, "Kaustos", paid=100)
        client.force_login(owner)

        assert (
            'value="none"' not in client.get(self.slot_line(gang).href).content.decode()
        )


class TestAPickTheGangHolds:
    """Treat valid gang-held picks as facts about every member, including the fighter who made the choice.

    Ordinary gang equipment does not satisfy conditions asking what a model holds.
    """

    @pytest.fixture
    @library_setup
    def slot_type(self, default_pack):
        return create_slot_type("Archetype", allows_repeats=False)

    @pytest.fixture
    @library_setup
    def mutant(self, slot_type):
        return create_pickable("Mutant", slot_type)

    @pytest.fixture
    @library_setup
    def leader(self, person_type, gang_type, slot_type, mutant):
        """Give the Leader a choice whose selected pick is stored on the gang."""
        picklist = create_picklist("Outcast Archetypes", slot_type, members=[mutant])
        slot = create_slot("Archetype", slot_type, picklist, assigned_to="gang")
        profile = create_profile("Outcast Leader", person_type, gang_type, price=120)
        add_built_in(profile, slot)
        return profile

    @pytest.fixture
    @library_setup
    def plain(self, person_type, gang_type):
        return create_profile("Scav", person_type, gang_type, price=40)

    def watcher(self, pickable, name="Watcher"):
        """Create equipment that grants a rule when its model matches the specified pick condition."""
        gear = create_wargear(name)
        modifier(
            f"{name}: notices {pickable}",
            targets_model_with(has_pickable(pickable)),
            ef_adds(create_rule(f"Noticed {pickable}")),
            carried_by=gear,
        )
        return gear

    def test_the_fighter_who_was_asked_holds_what_the_gang_chose(
        self, gang, leader, mutant
    ):
        boss = hire(gang, leader, "Boss", paid=120)
        assign(self.watcher(mutant), miniature=boss)
        (slot,) = choices_of(boss)

        choose(slot.anchor.assignment, mutant)

        _, computed = card_of(boss)
        assert [line.name for line in computed.rules] == ["Noticed Mutant"]
        assert_reconciled(gang)

    def test_and_so_does_everybody_else(self, gang, leader, plain, mutant):
        boss = hire(gang, leader, "Boss", paid=120)
        scav = hire(gang, plain, "Scav", paid=40)
        assign(self.watcher(mutant), miniature=scav)
        (slot,) = choices_of(boss)

        choose(slot.anchor.assignment, mutant)

        _, computed = card_of(scav)
        assert [line.name for line in computed.rules] == ["Noticed Mutant"]
        assert_reconciled(gang)

    def test_a_pick_the_bearer_holds_counts_the_same_way(self, gang, hunter, houses):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        assign(self.watcher(houses["Cawdor"]), miniature=kaustos)
        (slot,) = choices_of(kaustos)

        choose(slot.anchor.assignment, houses["Cawdor"])

        _, computed = card_of(kaustos)
        assert [line.name for line in computed.rules] == ["Noticed Cawdor"]
        assert_reconciled(gang)

    def test_a_gun_the_gang_holds_is_still_not_the_models(self, gang, leader, mutant):
        """Include gang-held picks in model matching without including ordinary gang equipment."""
        from n26.core import select

        boss = hire(gang, leader, "Boss", paid=120)
        arsenal = create_wargear("Gang Mortar")
        assign(arsenal, gang=gang)
        (slot,) = choices_of(boss)
        choose(slot.anchor.assignment, mutant)

        matchable = build_card(boss).model_matchable()

        assert select.Has(mutant).matches(matchable)
        assert not select.Has(arsenal).matches(matchable)

    def test_a_gang_held_pickable_with_no_choice_behind_it_says_nothing(
        self, gang, leader, mutant
    ):
        """Exclude an unanchored gang-held pickable from member pick conditions."""
        from n26.core import select

        boss = hire(gang, leader, "Boss", paid=120)
        assign(mutant, gang=gang)

        assert not select.Has(mutant).matches(build_card(boss).model_matchable())


class TestTwoChoicesOneThingGave:
    """Distinguish choices sharing the same granting assignment and slot type through each pick's recorded slot."""

    @pytest.fixture
    @library_setup
    def trees(self, default_pack):
        slot_type = create_slot_type("Skill Tree")
        pickables = {
            name: create_pickable(name, slot_type)
            for name in ("Agility", "Brawn", "Cunning")
        }
        picklist = create_picklist("Trees", slot_type, members=list(pickables.values()))
        first = create_slot("Tree one", slot_type, picklist, label="Skill tree 1")
        second = create_slot("Tree two", slot_type, picklist, label="Skill tree 2")
        charter = create_wargear("Venator Charter")
        modifier(
            "Charter: the first tree",
            targets_model(),
            ef_adds(first),
            carried_by=charter,
        )
        modifier(
            "Charter: the second tree",
            targets_model(),
            ef_adds(second),
            carried_by=charter,
        )
        return charter, pickables

    @pytest.fixture
    def venator(self, person_type, gang_type, gang, trees):
        charter, _ = trees
        profile = create_profile("Venator", person_type, gang_type, price=100)
        model = hire(gang, profile, "Kaustos", paid=100)
        assign(charter, miniature=model)
        return model

    def asked(self, miniature):
        return {slot.kind_label: slot for slot in choices_of(miniature)}

    def test_each_choice_holds_only_its_own_pick(self, gang, venator, trees):
        _, pickables = trees
        assert sorted(self.asked(venator)) == ["Skill tree 1", "Skill tree 2"]
        asked = self.asked(venator)

        choose(
            asked["Skill tree 1"].anchor.assignment,
            pickables["Agility"],
            slot=asked["Skill tree 1"].slot,
        )
        choose(
            asked["Skill tree 2"].anchor.assignment,
            pickables["Brawn"],
            slot=asked["Skill tree 2"].slot,
        )

        settled = self.asked(venator)
        assert {label: slot.chosen_name for label, slot in settled.items()} == {
            "Skill tree 1": "Agility",
            "Skill tree 2": "Brawn",
        }
        assert [len(slot.picks) for slot in settled.values()] == [1, 1]

        remove(Assignment.objects.get(pickable=pickables["Agility"], archived=False))
        asked = self.asked(venator)
        choose(
            asked["Skill tree 1"].anchor.assignment,
            pickables["Cunning"],
            slot=asked["Skill tree 1"].slot,
        )

        settled = self.asked(venator)
        assert {label: slot.chosen_name for label, slot in settled.items()} == {
            "Skill tree 1": "Cunning",
            "Skill tree 2": "Brawn",
        }
        assert_reconciled(gang)


class TestAChoiceBoughtIntoTheStash:
    """Host an equipment choice and its default pick in the stash when the purchase has no bearer."""

    @pytest.fixture
    @library_setup
    def banner(self, legacy, legacies, houses):
        gear = create_wargear("Ancestor Banner", price=20)
        slot = create_slot("Banner Legacy", legacy, legacies, label="Gang Legacy")
        add_built_in(gear, slot, default_pickable=houses["Cawdor"])
        return gear

    def test_the_purchase_goes_through(self, gang, banner, houses):
        """Give the default pick the same stash host as its purchase to satisfy the exactly-one-host constraint."""
        bought = buy(gang.stash, thing=banner, paid=20)

        assert bought.stash == gang.stash
        assert_reconciled(gang)

        pick = Assignment.objects.get(pickable=houses["Cawdor"], archived=False)
        assert pick.stash == gang.stash
        assert pick.chosen_for_slot is not None
        assert_reconciled(gang)

        assert Assignment.objects.get(pickable=houses["Cawdor"]).gang is None


class TestWhereAGivenChoiceIsDrawn:
    def test_it_takes_the_place_its_slot_was_given(
        self, gang, person_type, gang_type, legacy, legacies, houses
    ):
        """Order computed choices by the authored slot position alongside built-in choices."""
        early = create_slot("Early Legacy", legacy, legacies, label="Aa", position=0)
        late = create_slot("Late Legacy", legacy, legacies, label="Zz", position=9)
        charter = create_wargear("Charter")
        modifier(
            "Charter: the early one",
            targets_model(),
            ef_adds(early),
            carried_by=charter,
        )
        profile = create_profile("Wanderer", person_type, gang_type, price=100)
        add_built_in(profile, late)

        kaustos = hire(gang, profile, "Kaustos", paid=100)
        assign(charter, miniature=kaustos)

        assert [slot.kind_label for slot in choices_of(kaustos)] == ["Aa", "Zz"]


class TestTheWordingAListGivesAnPickable:
    """Use picklist-member labels in the picker and the pickable's own name on the card."""

    @pytest.fixture
    @library_setup
    def renamed(self, person_type, gang_type, legacy, houses):
        picklist = create_picklist(
            "The Old Houses",
            legacy,
            members=[(houses["Cawdor"], "House of Redemption")],
        )
        slot = create_slot("Old Legacy", legacy, picklist, label="Gang Legacy")
        profile = create_profile("Pilgrim", person_type, gang_type, price=100)
        add_built_in(profile, slot)
        return profile

    def test_the_picker_says_what_the_list_calls_it(self, gang, renamed, houses):
        kaustos = hire(gang, renamed, "Kaustos", paid=100)
        _, computed = card_of(kaustos)
        (slot,) = computed.choices

        offer = build_choice_offer(slot, computed)

        assert [
            pickable.name for group in offer.groups for pickable in group.options
        ] == ["House of Redemption"]

        choose(slot.anchor.assignment, houses["Cawdor"])

        assert [line.chosen for line in drawn_card(kaustos).choices] == ["Cawdor"]
        assert_reconciled(gang)


def pickable_key_of(pickable):
    return f"library.pickable:{pickable.pk}"


def button_labels(body):
    """Extract rendered button labels in page order."""
    return [
        button.get_text(" ", strip=True)
        for button in BeautifulSoup(body, "html.parser").find_all("button")
    ]


def picker_href(gang):
    """Return the linked choice on the gang's single fighter card."""
    from n26.core.views.choose import link_slots

    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    (card,) = sheet.models
    (line,) = card.questions
    return line.href


class TestAChoiceThatHoldsSeveral:
    """Add and remove one pick per request and return to the picker.

    At capacity, offer only removal controls. Selecting another result must
    not evict an existing pick.
    """

    @pytest.fixture
    @library_setup
    def twice(self, person_type, gang_type, legacy, legacies):
        slot = create_slot(
            "Two Legacies",
            legacy,
            legacies,
            label="Gang Legacies",
            min_picks=0,
            max_picks=2,
        )
        profile = create_profile("Wanderer", person_type, gang_type, price=100)
        add_built_in(profile, slot)
        return profile

    @pytest.fixture
    def wanderer(self, gang, twice, owner, client):
        client.force_login(owner)
        return hire(gang, twice, "Kaustos", paid=100)

    def offer_for(self, miniature):
        _, computed = card_of(miniature)
        (slot,) = computed.choices
        return build_choice_offer(slot, computed)

    def test_a_second_click_adds_rather_than_replacing_the_first(
        self, gang, wanderer, houses, client
    ):
        href = picker_href(gang)
        said = button_labels(client.get(href).content.decode())
        assert "Save" not in said
        assert said.count("Add") == 3
        assert_reconciled(gang)
        client.post(href, {"thing": pickable_key_of(houses["Cawdor"])})

        landed = client.post(href, {"thing": pickable_key_of(houses["Escher"])})

        (settled,) = choices_of(wanderer)
        assert sorted(node.name for node in settled.picks) == ["Cawdor", "Escher"]
        # Back to the same choice: the next pick is a click away.
        assert landed["Location"] == href
        assert_reconciled(gang)

        offer = self.offer_for(wanderer)

        assert [
            (pickable.name, pickable.is_current, pickable.control)
            for group in offer.groups
            for pickable in group.options
        ] == [("Cawdor", True, "remove"), ("Escher", True, "remove")]
        assert_reconciled(gang)

        from n26.core.models import DismissedOffer

        dismiss = href.replace("/choose/", "/offers/") + "dismiss/"

        reply = client.post(dismiss, follow=True)

        assert (
            "You cannot dismiss Gang Legacies. It has picks. Take them all back first."
            in reply.content.decode()
        )
        assert not DismissedOffer.objects.filter(gang=gang).exists()
        assert_reconciled(gang)

        body = client.get(href).content.decode()

        assert "Ironhead Squats" not in body
        assert button_labels(body).count("Remove") == 2
        assert_reconciled(gang)

        client.post(href, {"thing": pickable_key_of(houses["Ironhead Squats"])})

        (settled,) = choices_of(wanderer)
        assert sorted(node.name for node in settled.picks) == ["Cawdor", "Escher"]
        assert_reconciled(gang)

        client.post(href, {"remove": pickable_key_of(houses["Cawdor"])})

        (settled,) = choices_of(wanderer)
        assert [node.name for node in settled.picks] == ["Escher"]
        assert_reconciled(gang)

        client.post(href, {"thing": pickable_key_of(houses["Cawdor"])})
        client.post(href, {"remove": pickable_key_of(houses["Escher"])})

        body = client.get(href).content.decode()

        assert "Ironhead Squats" in body
        assert button_labels(body).count("Add") == 2
        assert_reconciled(gang)


class TestAChoiceThatHoldsNone:
    """A slot with zero capacity offers no selections and creates no picks."""

    @pytest.fixture
    @library_setup
    def asks_nothing(self, person_type, gang_type, legacy, legacies):
        slot = create_slot(
            "No Legacy",
            legacy,
            legacies,
            label="Gang Legacy",
            min_picks=0,
            max_picks=0,
        )
        profile = create_profile("Foundling", person_type, gang_type, price=100)
        add_built_in(profile, slot)
        return profile

    def test_a_click_that_reached_it_anyway_writes_nothing(
        self, gang, asks_nothing, houses, client, owner
    ):
        from django.urls import reverse

        kaustos = hire(gang, asks_nothing, "Kaustos", paid=100)
        client.force_login(owner)
        # No screen links the picker, so the address is built by hand.
        (slot,) = choices_of(kaustos)
        key = f"{kaustos.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"
        picker = reverse("n26-choose", args=[gang.pk, key])

        _, computed = card_of(kaustos)
        assert build_choice_offer(slot, computed).is_empty
        assert_reconciled(gang)
        for url in (
            reverse("n26-gang", args=[gang.pk]),
            reverse("n26-edit-fighter", args=[kaustos.pk]),
        ):
            body = client.get(url).content.decode()
            assert "Gang Legacy" in body
            assert picker not in body
            assert self.dismiss_href(gang, kaustos) not in body
            if url == reverse("n26-gang", args=[gang.pk]):
                row = body[body.index("Gang Legacy</dt>") :]
                row = row[: row.index("</dd>")]
                assert "Choose" not in row
                assert "Add" not in row

        client.post(picker, {"thing": pickable_key_of(houses["Cawdor"])})

        assert choices_of(kaustos)[0].picks == []
        assert not Assignment.objects.filter(
            pickable__isnull=False, archived=False
        ).exists()
        assert_reconciled(gang)

        from n26.core.models import DismissedOffer

        reply = client.post(self.dismiss_href(gang, kaustos), follow=True)

        assert "You cannot dismiss Gang Legacy. It offers nothing to choose." in (
            reply.content.decode()
        )
        assert not DismissedOffer.objects.filter(gang=gang).exists()

    def dismiss_href(self, gang, miniature):
        from django.urls import reverse

        (slot,) = choices_of(miniature)
        key = f"{miniature.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"
        return reverse("n26-dismiss-offer", args=[gang.pk, key])


class TestAChoiceTheGangIsAskedThatHoldsNone:
    """Display a zero-capacity gang choice without linking to an empty picker."""

    @pytest.fixture
    @library_setup
    def asks_the_gang_nothing(self, legacy, legacies):
        slot = create_slot(
            "No Legacy",
            legacy,
            legacies,
            label="Gang Legacy",
            assigned_to="gang",
            min_picks=0,
            max_picks=0,
        )
        made = create_gang_type("Outcasts")
        add_built_in(made, slot)
        return made

    def test_a_dismissal_written_for_it_hides_nothing(
        self, owner, asks_the_gang_nothing, client
    ):
        """Ignore stored dismissals for zero-capacity choices because no control can restore them."""
        from django.urls import reverse

        from n26.core.models import DismissedOffer
        from n26.core.views.choose import link_slots

        gang = found_gang("The Forgotten", asks_the_gang_nothing, owner=owner)
        sheet = render_gang(gang)
        link_slots(gang, sheet)
        (line,) = sheet.choices
        assert line.is_full and not line.is_resolved
        client.force_login(owner)

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Gang Legacy" in body
        assert reverse("n26-choose", args=[gang.pk, line.key]) not in body
        assert ">Choose<" not in body

        DismissedOffer.objects.create(gang=gang, slot_key=line.key)
        client.force_login(owner)

        for query in ("", "?dismissed=show"):
            body = client.get(
                reverse("n26-gang", args=[gang.pk]) + query
            ).content.decode()
            assert "Gang Legacy" in body
            assert reverse("n26-restore-offer", args=[gang.pk, line.key]) not in body


class TestARollTableInThePicker:
    """Order roll-table options by their bands and display each band before its result.

    Ordinary picklists have no bands.
    """

    @pytest.fixture
    @library_setup
    def injury(self, default_pack):
        return create_slot_type("Lasting Injury", allows_repeats=True)

    @pytest.fixture
    @library_setup
    def results(self, injury):
        # Added out of roll order, so order on screen is the table's.
        return [
            create_pickable("Eye Injury", injury),
            create_pickable("Lesson Learnt", injury),
            create_pickable("Out Cold", injury),
        ]

    @pytest.fixture
    def yolanda(self, gang, person_type, gang_type, injury, results):
        table = create_picklist(
            "Lasting Injury Table", injury, dice="d66", roll_selects="band"
        )
        for pickable, (low, high) in zip(
            results, [(51, 51), (11, 11), (21, 26)], strict=True
        ):
            add_picklist_member(table, pickable, roll_low=low, roll_high=high)
        slot = create_slot(
            "Lasting Injury",
            injury,
            table,
            label="Lasting Injuries",
            min_picks=0,
            max_picks=3,
        )
        profile = create_profile("Ganger", person_type, gang_type, price=50)
        add_built_in(profile, slot)
        return hire(gang, profile, "Yolanda", paid=50)

    def offer_for(self, miniature):
        _, computed = card_of(miniature)
        slot = next(s for s in computed.choices if s.kind_label == "Lasting Injuries")
        return build_choice_offer(slot, computed)

    def test_an_ordinary_list_carries_no_bands(self, gang, hunter, houses):
        sev = hire(gang, hunter, "Sev", paid=100)
        _, computed = card_of(sev)
        offer = build_choice_offer(next(iter(choices_of(sev))), computed)
        assert all(o.band == "" for g in offer.groups for o in g.options)
        assert_reconciled(gang)

    def test_the_page_leads_each_row_with_the_band(self, client, owner, gang, yolanda):

        from n26.core.views.choose import link_slots

        offer = self.offer_for(yolanda)
        rows = [(o.band, o.name) for g in offer.groups for o in g.options]
        assert rows == [
            ("11", "Lesson Learnt"),
            ("21-26", "Out Cold"),
            ("51", "Eye Injury"),
        ]
        assert_reconciled(gang)

        client.force_login(owner)
        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        href = next(
            line.href
            for card in sheet.models
            for line in card.questions
            if line.kind_label == "Lasting Injuries"
        )
        body = client.get(href).content.decode()
        assert "21-26" in body
        # The band sits just ahead of its result's name on the row.
        assert ">11<" in body[: body.index("Lesson Learnt")][-300:]
        assert_reconciled(gang)


class TestThePickerStaysFlatHoweverLongTheList:
    def test_the_page_reads_flat_as_the_list_grows(
        self, gang, hunter, legacy, legacies, client, owner, django_assert_num_queries
    ):
        """Load labels and pick identities with the list so adding options adds no page queries."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def grow(indices):
            for index in indices:
                add_picklist_member(legacies, create_pickable(f"House {index}", legacy))

        hire(gang, hunter, "Kaustos", paid=100)
        client.force_login(owner)
        href = picker_href(gang)

        grow(range(3))
        with CaptureQueriesContext(connection) as few:
            assert client.get(href).status_code == 200
        grow(range(3, 23))
        with django_assert_num_queries(len(few), exact=False):
            assert client.get(href).status_code == 200


class TestTheKindsKeepOutOfTheWay:
    def test_neither_is_gear_the_trading_post_would_stock(self):
        """Exclude slots and pickables from the GEAR family used by Trading Post sweeps."""
        from n26.library.models.assignable import Family

        assert Pickable.family != Family.GEAR
        assert Slot.family != Family.GEAR

    def test_neither_says_its_kind_to_a_player(self, legacy, houses):
        """Use authored pick names without an internal kind label."""
        from n26.core.effects import kind_of

        assert kind_of(houses["Cawdor"]) == ""


class TestAChoiceThatAllowsRepeats:
    """Combine slot capacity with the slot type's repeat policy.

    A repeated injury creates another pick assignment and another effect;
    the card groups repeated result names with a count.
    """

    @pytest.fixture
    @library_setup
    def injury(self, default_pack):
        return create_slot_type(
            "Lasting Injury", plural_name="Lasting Injuries", allows_repeats=True
        )

    @pytest.fixture
    @library_setup
    def results(self, injury, person_type):
        from n26.library.models import Stat

        eye = create_pickable("Eye Injury", injury)
        modifier(
            "Eye Injury: worsens WS",
            targets_model(),
            changes_stat(Stat.objects.get(short_name="WS"), "worsen", 1),
            carried_by=eye,
        )
        return {
            "Eye Injury": eye,
            "Out Cold": create_pickable("Out Cold", injury),
        }

    @pytest.fixture
    @library_setup
    def injuries(self, injury, results):
        return create_picklist(
            "Lasting Injury Table", injury, members=list(results.values())
        )

    @pytest.fixture
    @library_setup
    def injury_slot(self, injury, injuries):
        return create_slot(
            "Lasting Injury",
            injury,
            injuries,
            label="Lasting Injuries",
            min_picks=0,
            max_picks=3,
        )

    @pytest.fixture
    def yolanda(self, gang, person_type, gang_type, injury_slot):
        profile = create_profile("Ganger", person_type, gang_type, price=50)
        add_built_in(profile, injury_slot)
        return hire(gang, profile, "Yolanda", paid=50)

    def _slot(self, miniature):
        return next(
            s for s in choices_of(miniature) if s.kind_label == "Lasting Injuries"
        )

    def _line(self, miniature):
        return next(
            line
            for line in drawn_card(miniature).choices
            if line.kind_label == "Lasting Injuries"
        )

    def _pick(self, miniature, thing):
        choose(self._slot(miniature).anchor.assignment, thing)

    def test_the_same_result_is_held_twice_and_reads_as_a_count(self, yolanda, results):
        line = self._line(yolanda)
        assert not line.is_resolved
        assert not line.is_full
        self._pick(yolanda, results["Eye Injury"])

        _, computed = card_of(yolanda)
        offer = build_choice_offer(self._slot(yolanda), computed)
        held = next(
            o for g in offer.groups for o in g.options if o.name == "Eye Injury"
        )
        assert held.is_current
        assert held.control == "both"

        self._pick(yolanda, results["Eye Injury"])

        picks = [p.assignable for p in self._slot(yolanda).picks]
        assert picks == [results["Eye Injury"]] * 2
        assert self._line(yolanda).chosen == "Eye Injury (x2)"

        _, computed = card_of(yolanda)
        from_eye = [c for c in computed.stat_changes if c.source == "Eye Injury"]
        assert len(from_eye) == 2

        assert (
            Assignment.objects.filter(
                pickable=results["Eye Injury"], archived=False
            ).count()
            == 2
        )

        remove(self._slot(yolanda).anchor.assignment)

        assert not Assignment.objects.filter(
            pickable=results["Eye Injury"], archived=False
        ).exists()
        assert not any(
            line.kind_label == "Lasting Injuries"
            for line in drawn_card(yolanda).choices
        )
        _, computed = card_of(yolanda)
        assert not any(c.source == "Eye Injury" for c in computed.stat_changes)
        yolanda.gang.refresh_from_db()
        assert_reconciled(yolanda.gang)

    def test_a_later_repeat_joins_the_first_of_its_name(self, yolanda, results):
        self._pick(yolanda, results["Eye Injury"])
        self._pick(yolanda, results["Out Cold"])
        self._pick(yolanda, results["Eye Injury"])

        assert self._line(yolanda).chosen == "Eye Injury (x2), Out Cold"

    def test_the_card_keeps_asking_until_it_is_full(self, yolanda, results):
        self._pick(yolanda, results["Out Cold"])
        line = self._line(yolanda)
        assert line.is_resolved and not line.is_full

        self._pick(yolanda, results["Eye Injury"])
        self._pick(yolanda, results["Eye Injury"])
        assert self._line(yolanda).is_full

    def test_where_repeats_are_not_allowed_a_held_pick_is_only_removable(
        self, gang, person_type, gang_type, legacy, houses
    ):
        """Offer only removal for a held result when the multi-pick choice forbids repeats."""
        picklist = create_picklist(
            "Two Legacies", legacy, members=list(houses.values())
        )
        slot = create_slot("Two Legacies", legacy, picklist, max_picks=2)
        profile = create_profile("Twice Hunter", person_type, gang_type, price=100)
        add_built_in(profile, slot)
        sev = hire(gang, profile, "Sev", paid=100)

        choose(next(iter(choices_of(sev))).anchor.assignment, houses["Cawdor"])

        _, computed = card_of(sev)
        offer = build_choice_offer(next(iter(choices_of(sev))), computed)
        held = next(o for g in offer.groups for o in g.options if o.name == "Cawdor")
        assert held.control == "remove"


class TestAChoiceThatAllowsRepeatsOnScreen:
    """Add repeated results through the picker and retain the card's Add control until capacity is reached."""

    @pytest.fixture
    @library_setup
    def injury(self, default_pack):
        return create_slot_type(
            "Lasting Injury", plural_name="Lasting Injuries", allows_repeats=True
        )

    @pytest.fixture
    @library_setup
    def results(self, injury):
        return {
            name: create_pickable(name, injury) for name in ("Eye Injury", "Out Cold")
        }

    @pytest.fixture
    @library_setup
    def ganger(self, person_type, gang_type, injury, results):
        picklist = create_picklist(
            "Lasting Injury Table", injury, members=list(results.values())
        )
        slot = create_slot(
            "Lasting Injury",
            injury,
            picklist,
            label="Lasting Injuries",
            min_picks=0,
            max_picks=2,
        )
        profile = create_profile("Ganger", person_type, gang_type, price=50)
        add_built_in(profile, slot)
        return profile

    @pytest.fixture
    def yolanda(self, gang, ganger):
        return hire(gang, ganger, "Yolanda", paid=50)

    def _href(self, gang):
        from django.urls import reverse

        from n26.core.views.choose import link_slots

        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        line = next(
            line
            for card in sheet.models
            for line in card.questions
            if line.kind_label == "Lasting Injuries"
        )
        return line.href, reverse("n26-gang", args=[gang.pk])

    def _post(self, client, href, thing):
        return client.post(href, {"thing": f"{thing._meta.label_lower}:{thing.pk}"})

    def test_a_second_click_on_a_held_result_is_a_second_pick(
        self, client, owner, gang, yolanda, results
    ):
        client.force_login(owner)
        href, sheet_url = self._href(gang)
        eye = results["Eye Injury"]

        from django.contrib.messages import get_messages

        response = self._post(client, href, eye)
        assert response.status_code == 302
        said = [str(m) for m in get_messages(response.wsgi_request)]
        assert any(m.startswith("Added Eye Injury") for m in said), said

        body = client.get(href).content.decode()
        assert 'aria-label="Remove Eye Injury"' in body
        assert 'aria-label="Add Eye Injury again"' in body
        # The result not yet held offers only the one way in.
        assert 'aria-label="Add Out Cold"' in body
        assert 'aria-label="Remove Out Cold"' not in body

        assert self._post(client, href, eye).status_code == 302

        assert Assignment.objects.filter(pickable=eye, archived=False).count() == 2
        assert_reconciled(gang)

        body = client.get(sheet_url).content.decode()
        # The row, not the flash message that also names the choice.
        row = body[body.index("Lasting Injuries</dt>") :]
        assert "Eye Injury (x2)" in row
        assert "Eye Injury, Eye Injury" not in row
        assert "Add" not in row[: row.index("</dd>")]

        response = self._post(client, href, eye)
        assert response.status_code == 302
        assert Assignment.objects.filter(pickable=eye, archived=False).count() == 2

        said = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("holds all the picks" in m for m in said)

    def test_the_card_keeps_its_choose_beside_a_held_result(
        self, client, owner, gang, yolanda, results
    ):
        client.force_login(owner)
        href, sheet_url = self._href(gang)
        self._post(client, href, results["Out Cold"])

        body = client.get(sheet_url).content.decode()
        # The row, not the flash message that also names the choice.
        row = body[body.index("Lasting Injuries</dt>") :]
        assert "Out Cold" in row
        assert "Add" in row[: row.index("</dd>")]

    def test_the_sheet_reads_flat_however_many_are_hurt(
        self, client, owner, gang, ganger, yolanda, results
    ):
        """Determine remaining capacity from loaded picks without adding page queries per injured model."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(owner)
        href, sheet_url = self._href(gang)
        self._post(client, href, results["Eye Injury"])
        with CaptureQueriesContext(connection) as few:
            assert client.get(sheet_url).status_code == 200

        for name in ("Mad Donna", "Kaustos"):
            hurt = hire(gang, ganger, name, paid=50)
            self._post(client, self._href_of(gang, hurt), results["Out Cold"])
        with CaptureQueriesContext(connection) as more:
            assert client.get(sheet_url).status_code == 200
        assert len(more) <= len(few)

    def _href_of(self, gang, miniature):
        from n26.core.views.choose import link_slots

        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        card = next(c for c in sheet.models if c.name == miniature.name)
        return next(
            line.href
            for line in card.questions
            if line.kind_label == "Lasting Injuries"
        )


class TestAPickMayAddToRating:
    """Record a pickable's rating contribution without charging credits.

    Removing the pick reverses that rating without moving money. Generic owned
    assignment endpoints do not expose sell, refund, reassign or remove actions
    for these picks.
    """

    @pytest.fixture
    @library_setup
    def boost(self, default_pack):
        return create_slot_type("Power Boost", allows_repeats=True)

    @pytest.fixture
    @library_setup
    def results(self, boost):
        return {
            "Combat Neuroware": create_pickable(
                "Combat Neuroware", boost, rating_contribution=20
            ),
            "Improved Motive Power": create_pickable(
                "Improved Motive Power", boost, rating_contribution=10
            ),
            "Nothing Happens": create_pickable("Nothing Happens", boost),
        }

    @pytest.fixture
    @library_setup
    def power_boost_slot(self, boost, results):
        table = create_picklist("Power Boost", boost, members=list(results.values()))
        return create_slot("Power Boost", boost, table, min_picks=0, max_picks=3)

    @pytest.fixture
    @library_setup
    def spyrer(self, person_type, gang_type, power_boost_slot):
        profile = create_profile("Spyrer", person_type, gang_type, price=200)
        add_built_in(profile, power_boost_slot)
        return profile

    @pytest.fixture
    @library_setup
    def boosted_spyrer(self, person_type, gang_type, power_boost_slot, results):
        """Apply an initial pick's rating contribution during hire, as for a manually chosen pick."""
        profile = create_profile("Boosted Spyrer", person_type, gang_type, price=200)
        add_built_in(
            profile, power_boost_slot, default_pickable=results["Combat Neuroware"]
        )
        return profile

    def _boost_slot(self, miniature):
        return next(
            line for line in choices_of(miniature) if line.kind_label == "Power Boost"
        )

    def test_the_pick_adds_its_rating_and_moves_no_credits(
        self, client, owner, gang, spyrer, results
    ):
        orrus = hire(gang, spyrer, "Orrus", paid=200)
        gang.refresh_from_db()
        credits_before, rating_before = gang.credits, gang.rating

        pick = choose(
            self._boost_slot(orrus).anchor.assignment, results["Combat Neuroware"]
        )

        gang.refresh_from_db()
        orrus.refresh_from_db()
        assert gang.credits == credits_before
        assert gang.rating == rating_before + 20
        assert orrus.rating == 220
        entry = pick.ledger_entry
        assert (entry.paid, entry.list_price, entry.rating_contribution) == (0, 0, 20)
        assert_reconciled(gang)

        from django.urls import reverse

        client.force_login(owner)

        for route in ("n26-sell", "n26-refund", "n26-reassign", "n26-remove"):
            assert client.post(reverse(route, args=[pick.pk])).status_code == 404, route

        gang.refresh_from_db()
        credits_before = gang.credits

        remove(pick)

        gang.refresh_from_db()
        orrus.refresh_from_db()
        assert gang.credits == credits_before
        assert orrus.rating == 200
        assert_reconciled(gang)

    def test_a_pickable_that_adds_nothing_still_adds_nothing(
        self, gang, spyrer, results
    ):
        orrus = hire(gang, spyrer, "Orrus", paid=200)
        gang.refresh_from_db()
        before = gang.rating

        choose(self._boost_slot(orrus).anchor.assignment, results["Nothing Happens"])

        gang.refresh_from_db()
        assert gang.rating == before
        assert_reconciled(gang)

    def test_picks_stack_and_each_adds_its_own(self, gang, spyrer, results):
        orrus = hire(gang, spyrer, "Orrus", paid=200)
        anchor = self._boost_slot(orrus).anchor.assignment

        choose(anchor, results["Combat Neuroware"])
        choose(anchor, results["Improved Motive Power"])

        orrus.refresh_from_db()
        gang.refresh_from_db()
        assert orrus.rating == 230
        assert_reconciled(gang)

    def test_a_starting_pick_carries_its_rating_too(self, gang, boosted_spyrer):
        orrus = hire(gang, boosted_spyrer, "Orrus", paid=200)

        orrus.refresh_from_db()
        assert orrus.rating == 220
        assert self._boost_slot(orrus).chosen_name == "Combat Neuroware"
        assert_reconciled(gang)

    def test_a_pick_the_gang_holds_adds_nothing(
        self, gang, person_type, gang_type, boost, results
    ):
        """Keep gang-hosted picks at zero rating regardless of the pickable's authored contribution."""
        table = create_picklist("Gang Boost", boost, members=list(results.values()))
        gang_slot = create_slot(
            "Gang Boost", boost, table, min_picks=0, max_picks=1, assigned_to="gang"
        )
        profile = create_profile("Rig Master", person_type, gang_type, price=200)
        add_built_in(profile, gang_slot)
        master = hire(gang, profile, "Orrus", paid=200)
        gang.refresh_from_db()
        before = gang.rating
        anchor = next(
            line for line in choices_of(master) if line.kind_label == "Gang Boost"
        ).anchor.assignment

        pick = choose(anchor, results["Combat Neuroware"])

        gang.refresh_from_db()
        assert pick.gang_id == gang.pk and pick.miniature_id is None
        assert pick.ledger_entry.rating_contribution == 0
        assert gang.rating == before
        assert_reconciled(gang)

    def test_an_explicit_rating_wins(self, gang, spyrer, results):
        orrus = hire(gang, spyrer, "Orrus", paid=200)

        pick = choose(
            self._boost_slot(orrus).anchor.assignment,
            results["Combat Neuroware"],
            rating=5,
        )

        assert pick.ledger_entry.rating_contribution == 5
        gang.refresh_from_db()
        assert_reconciled(gang)
