"""Slots and picks: a choice made from a curated list.

The shape a new domain of choice is authored in rather than coded: a
slot type, its options, the list they are offered on, and the choice
itself. Gang Legacy is the first use — eight houses, each opening that
house's equipment list to whoever picks it.

What this file holds still is the engine underneath: that assigning a
slot asks the question, that the pick is read off ``chosen_for`` and
nothing is inferred from kinds, that an option with no choice behind it
does nothing at all, and that a choice a pick opens goes when that pick
does. The screens are `test_choosing.py`'s.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.models import Assignment
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_choice_offer, build_model_card, render_gang
from n26.library.authoring import targets_model as targets_model_with
from n26.library.models import Pickable, Slot
from n26.tests.sandbox.actions import (
    add_built_in,
    add_picklist_member,
    assign,
    buy,
    choose,
    create_collection,
    create_gang_type,
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
    remove,
    targets_model,
)

pytestmark = pytest.mark.django_db


# --- Example A: Gang Legacy, eight houses, one choice ----------------------


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def legacy(default_pack):
    """The domain. Nobody picks two legacies."""
    return create_slot_type(
        "Gang Legacy", plural_name="Gang Legacies", allows_repeats=False
    )


@pytest.fixture
def houses(legacy):
    """Three of the eight, each opening its own equipment list."""
    made = {}
    for name in ("Cawdor", "Escher", "Ironhead Squats"):
        option = create_pickable(name, legacy)
        modifier(
            f"{name}: its equipment list",
            targets_model(),
            ef_adds(create_collection(f"House {name} Equipment List")),
            carried_by=option,
        )
        made[name] = option
    return made


@pytest.fixture
def legacies(legacy, houses):
    return create_picklist("Gang Legacies", legacy, members=list(houses.values()))


@pytest.fixture
def gang_legacy_slot(legacy, legacies):
    return create_slot("Gang Legacy", legacy, legacies)


@pytest.fixture
def hunter(person_type, gang_type, gang_legacy_slot):
    """A profile carrying the choice: hired plain, it arrives open."""
    profile = create_profile("Hunter", person_type, gang_type, price=100)
    add_built_in(profile, gang_legacy_slot)
    return profile


@pytest.fixture
def squats_hunter(person_type, gang_type, gang_legacy_slot, houses):
    """The slot-with-default: hired, it arrives already settled."""
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


class TestAChoiceArrivesOpen:
    """Assigning a slot is what asks the question. Nothing pending is
    written: the row is computed, and leaving it open costs nothing."""

    def test_the_card_asks_it_by_its_label(self, gang, hunter):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)

        (slot,) = choices_of(kaustos)

        assert slot.kind_label == "Gang Legacy"
        assert not slot.is_resolved
        assert (slot.min_picks, slot.max_picks) == (1, 1)
        assert_reconciled(gang)

    def test_the_slot_itself_draws_no_line(self, gang, hunter):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        drawn = drawn_card(kaustos)

        assert [line.name for line in drawn.equipment] == []
        assert [line.kind_label for line in drawn.choices] == ["Gang Legacy"]

    def test_the_card_says_when_it_is_short(self, gang, hunter):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        drawn = drawn_card(kaustos)

        assert [note.text for note in drawn.remarks] == ["Gang Legacy — 0 of 1 chosen"]

    def test_nothing_is_refused_for_leaving_it_open(self, gang, hunter):
        """Inform, never police: the note is the whole of it."""
        hire(gang, hunter, "Kaustos", paid=100)
        assert_reconciled(gang)


class TestMakingTheChoice:
    def test_the_pick_answers_the_row_and_draws_no_row_of_its_own(
        self, gang, hunter, houses
    ):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (open_slot,) = choices_of(kaustos)

        choose(open_slot.anchor.assignment, houses["Cawdor"])

        _, computed = card_of(kaustos)
        (settled,) = computed.choices
        assert settled.chosen_name == "Cawdor"
        drawn = drawn_card(kaustos)
        assert [line.name for line in drawn.equipment] == []
        assert [line.chosen for line in drawn.choices] == ["Cawdor"]
        assert drawn.remarks == []

    def test_what_the_pick_gives_reaches_the_bearer(self, gang, hunter, houses):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (open_slot,) = choices_of(kaustos)

        choose(open_slot.anchor.assignment, houses["Cawdor"])

        _, computed = card_of(kaustos)
        assert [line.name for line in computed.collections] == [
            "House Cawdor Equipment List"
        ]

    def test_the_pick_is_free_and_the_gang_is_worth_the_same(
        self, gang, hunter, houses
    ):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (open_slot,) = choices_of(kaustos)
        before = gang.rating

        choose(open_slot.anchor.assignment, houses["Cawdor"])

        gang.refresh_from_db()
        assert gang.rating == before
        assert_reconciled(gang)

    def test_a_pick_from_another_domain_settles_nothing_and_is_refused(
        self, gang, hunter, default_pack
    ):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (open_slot,) = choices_of(kaustos)
        elsewhere = create_pickable("Aranthian", create_slot_type("Affiliation"))

        with pytest.raises(Refusal, match="Aranthian cannot settle Gang Legacy"):
            choose(open_slot.anchor.assignment, elsewhere)

    def test_an_option_the_list_does_not_offer_is_still_the_owners_to_give(
        self, gang, hunter, legacy
    ):
        """The narrowing informs and never polices — an owner may hand
        over an off-list option of the right domain."""
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (open_slot,) = choices_of(kaustos)
        unlisted = create_pickable("Delaque", legacy)

        choose(open_slot.anchor.assignment, unlisted)

        (settled,) = choices_of(kaustos)
        assert settled.chosen_name == "Delaque"


class TestASlotWithADefault:
    """Hired from a profile carrying the pick, the choice arrives made."""

    def test_it_arrives_settled(self, gang, squats_hunter):
        grendel = hire(gang, squats_hunter, "Grendel", paid=100)

        (settled,) = choices_of(grendel)

        assert settled.chosen_name == "Ironhead Squats"
        assert_reconciled(gang)

    def test_the_pick_answers_the_slots_own_assignment(self, gang, squats_hunter):
        grendel = hire(gang, squats_hunter, "Grendel", paid=100)

        slot = Assignment.objects.get(slot__isnull=False, miniature_root=grendel)
        pick = Assignment.objects.get(pickable__isnull=False, miniature_root=grendel)
        assert pick.chosen_for == slot
        assert pick.caused_by == slot

    def test_changing_it_is_the_ordinary_rechoose(self, gang, squats_hunter, houses):
        grendel = hire(gang, squats_hunter, "Grendel", paid=100)
        (settled,) = choices_of(grendel)

        remove(settled.picks[0].assignment)
        choose(settled.anchor.assignment, houses["Escher"])

        (rechosen,) = choices_of(grendel)
        assert rechosen.chosen_name == "Escher"
        assert_reconciled(gang)

    def test_the_choice_stays_when_the_pick_goes(self, gang, squats_hunter):
        grendel = hire(gang, squats_hunter, "Grendel", paid=100)
        (settled,) = choices_of(grendel)

        remove(settled.picks[0].assignment)

        (still_asked,) = choices_of(grendel)
        assert not still_asked.is_resolved


class TestTwoChoicesOfOneDomain:
    """Two slots of one type on one holder stay independent, because a
    pick names the assignment that asked and not the slot row."""

    @pytest.fixture
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

    def test_the_card_says_when_one_option_answers_both(
        self, gang, twice_asked, houses
    ):
        """The domain forbids repeats, so picking Cawdor twice is worth
        mentioning — on the model's own card, where the choices are."""
        kaustos = hire(gang, twice_asked, "Kaustos", paid=100)
        for slot in choices_of(kaustos):
            choose(slot.anchor.assignment, houses["Cawdor"])

        drawn = drawn_card(kaustos)

        assert "Cawdor is chosen for both Legacy 1 and Legacy 2" in [
            note.text for note in drawn.remarks
        ]

    def test_a_domain_that_allows_repeats_says_nothing(
        self, gang, person_type, gang_type, default_pack
    ):
        domain = create_slot_type("Loadout", allows_repeats=True)
        option = create_pickable("Heavy", domain)
        picklist = create_picklist("Loadouts", domain, members=[option])
        profile = create_profile("Twice-armed", person_type, gang_type, price=100)
        add_built_in(profile, create_slot("Loadout 1", domain, picklist))
        add_built_in(profile, create_slot("Loadout 2", domain, picklist))

        kaustos = hire(gang, profile, "Kaustos", paid=100)
        for slot in choices_of(kaustos):
            choose(slot.anchor.assignment, option)

        drawn = drawn_card(kaustos)
        assert [note.text for note in drawn.remarks] == []


class TestThePickerMarksWhatIsTaken:
    """Where the domain takes one option once, the picker says which of
    its options this holder has already spent elsewhere.

    Marked and never withheld: the click still works, and what the card
    says about picking the same thing twice is said afterwards, on the
    card. The one hard refusal in the app is the founding budget.
    """

    @pytest.fixture
    def twice_asked(self, person_type, gang_type, legacy, legacies):
        profile = create_profile("Twice-born", person_type, gang_type, price=100)
        add_built_in(profile, create_slot("Legacy 1", legacy, legacies))
        add_built_in(profile, create_slot("Legacy 2", legacy, legacies))
        return profile

    def offers(self, miniature):
        """Both pickers, in the order the slots are named."""
        from n26.core.render import build_choice_offer

        _, computed = card_of(miniature)
        return [
            build_choice_offer(slot, computed)
            for slot in sorted(computed.choices, key=lambda slot: slot.source)
        ]

    def marks(self, offer):
        return {
            option.name: option.taken_for
            for group in offer.groups
            for option in group.options
        }

    def test_the_option_the_other_choice_holds_is_marked(
        self, gang, twice_asked, houses
    ):
        kaustos = hire(gang, twice_asked, "Kaustos", paid=100)
        first, _ = sorted(choices_of(kaustos), key=lambda slot: slot.source)
        choose(first.anchor.assignment, houses["Cawdor"])

        _, second = self.offers(kaustos)

        assert self.marks(second) == {
            "Cawdor": "Legacy 1",
            "Escher": "",
            "Ironhead Squats": "",
        }

    def test_the_choice_it_answers_calls_it_the_current_pick_instead(
        self, gang, twice_asked, houses
    ):
        """A choice does not report itself: what is picked here is
        already drawn as the answer, which is a different fact."""
        kaustos = hire(gang, twice_asked, "Kaustos", paid=100)
        first, _ = sorted(choices_of(kaustos), key=lambda slot: slot.source)
        choose(first.anchor.assignment, houses["Cawdor"])

        here, _ = self.offers(kaustos)
        (cawdor,) = [
            option
            for group in here.groups
            for option in group.options
            if option.name == "Cawdor"
        ]

        assert (cawdor.taken_for, cawdor.is_current) == ("", True)

    def test_a_domain_that_allows_repeats_marks_nothing(
        self, gang, person_type, gang_type, default_pack
    ):
        domain = create_slot_type("Loadout", allows_repeats=True)
        option = create_pickable("Heavy", domain)
        picklist = create_picklist("Loadouts", domain, members=[option])
        profile = create_profile("Twice-armed", person_type, gang_type, price=100)
        add_built_in(profile, create_slot("Loadout 1", domain, picklist))
        add_built_in(profile, create_slot("Loadout 2", domain, picklist))
        kaustos = hire(gang, profile, "Kaustos", paid=100)
        first, _ = sorted(choices_of(kaustos), key=lambda slot: slot.source)
        choose(first.anchor.assignment, option)

        _, second = self.offers(kaustos)

        assert self.marks(second) == {"Heavy": ""}

    def test_the_screen_says_so_and_still_offers_it(
        self, gang, twice_asked, houses, client, owner
    ):
        import re

        from n26.core.views.choose import link_slots

        kaustos = hire(gang, twice_asked, "Kaustos", paid=100)
        first, _ = sorted(choices_of(kaustos), key=lambda slot: slot.source)
        choose(first.anchor.assignment, houses["Cawdor"])
        client.force_login(owner)

        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        (card,) = sheet.models
        second = sorted(card.questions, key=lambda line: line.kind_label)[1]
        body = client.get(second.href).content.decode()

        assert "already chosen for Legacy 1" in body
        # Marked, not locked: the option is still a control that works.
        control = re.search(
            rf'<input[^>]*value="library.pickable:{houses["Cawdor"].pk}"[^>]*>', body
        )
        assert control and "disabled" not in control.group()


class TestAnOptionWithNoChoiceBehindIt:
    """A pickable an owner hands over with no slot to answer shows
    nothing and does nothing — not a line, not a modifier, not a fact
    another rule can match on."""

    @pytest.fixture
    def loud(self, legacy, default_pack):
        """An option that would be impossible to miss if it ran."""
        option = create_pickable("Cawdor", legacy)
        modifier(
            "Cawdor: a rule",
            targets_model(),
            ef_adds(create_rule("House Cawdor")),
            carried_by=option,
        )
        return option

    @pytest.fixture
    def plain_hunter(self, person_type, gang_type):
        return create_profile("Hunter", person_type, gang_type, price=100)

    def test_its_modifiers_do_not_run(self, gang, plain_hunter, loud):
        kaustos = hire(gang, plain_hunter, "Kaustos", paid=100)
        assign(loud, miniature=kaustos)

        _, computed = card_of(kaustos)

        assert [line.name for line in computed.rules] == []

    def test_it_draws_nothing(self, gang, plain_hunter, loud):
        kaustos = hire(gang, plain_hunter, "Kaustos", paid=100)
        assign(loud, miniature=kaustos)

        drawn = drawn_card(kaustos)

        assert [line.name for line in drawn.equipment] == []
        assert drawn.choices == []

    def test_no_rule_can_match_on_it(self, gang, plain_hunter, loud, default_pack):
        """A scope naming the pick reaches whoever chose it, and nobody
        chose this one."""
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

    def test_the_same_option_chosen_properly_does_everything(
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
    """A hidden slot draws no row at all while its pick applies in full
    — several things arriving together under one name."""

    @pytest.fixture
    def bundled(self, person_type, gang_type, legacy, legacies, houses, default_pack):
        slot = create_slot("Hidden legacy", legacy, legacies, hidden=True)
        profile = create_profile("Bundled", person_type, gang_type, price=100)
        add_built_in(profile, slot, default_pickable=houses["Cawdor"])
        return profile

    def test_no_choice_row_is_drawn(self, gang, bundled):
        kaustos = hire(gang, bundled, "Kaustos", paid=100)

        assert choices_of(kaustos) == []
        assert drawn_card(kaustos).choices == []

    def test_what_the_pick_gives_still_arrives(self, gang, bundled):
        kaustos = hire(gang, bundled, "Kaustos", paid=100)

        _, computed = card_of(kaustos)

        assert [line.name for line in computed.collections] == [
            "House Cawdor Equipment List"
        ]

    def test_and_it_says_nothing_about_being_short(self, gang, bundled):
        kaustos = hire(gang, bundled, "Kaustos", paid=100)
        drawn = drawn_card(kaustos)

        assert drawn.remarks == []


class TestAChoiceTheGangIsAsked:
    """A slot the gang holds is asked once, on the gang's own card. It
    rides every member's card so its behaviour reaches them; the
    question is the gang's."""

    @pytest.fixture
    def gang_type_with_affiliation(self, default_pack):
        domain = create_slot_type("Affiliation")
        aranthian = create_pickable("Aranthian", domain)
        picklist = create_picklist("Affiliations", domain, members=[aranthian])
        slot = create_slot(
            "Affiliation", domain, picklist, assigned_to="gang", min_picks=1
        )
        made = create_gang_type("Outcasts")
        add_built_in(made, slot)
        return made, aranthian

    def test_the_gangs_card_asks_it(self, owner, gang_type_with_affiliation):
        made, _ = gang_type_with_affiliation
        gang = found_gang("The Outcasts", made, owner=owner, budget=1000)

        (slot,) = gang_choices(gang).choices

        assert slot.kind_label == "Affiliation"
        assert not slot.is_resolved

    def test_no_members_card_asks_it_again(
        self, owner, gang_type_with_affiliation, person_type
    ):
        made, _ = gang_type_with_affiliation
        gang = found_gang("The Outcasts", made, owner=owner, budget=1000)
        profile = create_profile("Outcast", person_type, made, price=50)
        kaustos = hire(gang, profile, "Kaustos", paid=50)

        assert choices_of(kaustos) == []
        assert_reconciled(gang)

    def test_the_shortfall_is_the_gangs_news(self, owner, gang_type_with_affiliation):
        made, _ = gang_type_with_affiliation
        gang = found_gang("The Outcasts", made, owner=owner, budget=1000)

        assert "Affiliation — 0 of 1 chosen" in [
            note.text for note in gang_choices(gang).notes
        ]

    def test_the_pick_lands_on_the_gang(self, owner, gang_type_with_affiliation):
        made, aranthian = gang_type_with_affiliation
        gang = found_gang("The Outcasts", made, owner=owner, budget=1000)
        (slot,) = gang_choices(gang).choices

        choose(slot.anchor.assignment, aranthian)

        written = Assignment.objects.get(pickable=aranthian)
        assert written.gang == gang
        assert gang_choices(gang).choices[0].chosen_name == "Aranthian"


class TestALeaderAskedForTheGang:
    """The Leader → Gang arrow: the choice rides the leader, and what he
    picks belongs to the gang.

    The pick is gang-hosted, so its payload is broadcast — and scoped, so
    it reaches the ranks the archetype names and no others. Which ranks
    those are is content: naming a second one is a row on the condition,
    not a change here.
    """

    @pytest.fixture
    def ranks(self, default_pack):
        return {
            name.lower(): create_subtype(name)
            for name in ("Ganger", "Hive Scum", "Champion")
        }

    @pytest.fixture
    def leader(self, person_type, gang_type, ranks, default_pack):
        domain = create_slot_type("Archetype", allows_repeats=False)
        mutant = create_pickable("Mutant", domain)
        modifier(
            "Mutant: the gangers and the scum",
            targets_model_with(has_subtypes(ranks["ganger"], ranks["hive scum"])),
            ef_adds(create_rule("Unstable")),
            carried_by=mutant,
        )
        picklist = create_picklist("Outcast Archetypes", domain, members=[mutant])
        slot = create_slot("Archetype", domain, picklist, assigned_to="gang")
        profile = create_profile("Outcast Leader", person_type, gang_type, price=120)
        add_built_in(profile, slot)
        return profile, mutant

    def test_the_leaders_card_asks_it(self, gang, leader):
        profile, _ = leader
        boss = hire(gang, profile, "Boss", paid=120)

        (slot,) = choices_of(boss)

        assert slot.kind_label == "Archetype"

    def test_what_he_picks_is_the_gangs(self, gang, leader):
        profile, mutant = leader
        boss = hire(gang, profile, "Boss", paid=120)
        (slot,) = choices_of(boss)

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
    """A pick may give a further slot. Un-choosing retracts the chain
    through the cause: the given choice goes, and so does its answer."""

    @pytest.fixture
    def chained(self, person_type, gang_type, default_pack):
        domain = create_slot_type("Affiliation")
        houses_domain = create_slot_type("House")
        cawdor = create_pickable("House Cawdor", houses_domain)
        house_list = create_picklist("Clan Houses", houses_domain, members=[cawdor])
        house_slot = create_slot("House", houses_domain, house_list)

        clan_house = create_pickable("Clan House", domain)
        modifier(
            "Clan House: which house",
            targets_model(),
            ef_adds(house_slot),
            carried_by=clan_house,
        )
        affiliations = create_picklist("Affiliations", domain, members=[clan_house])
        first = create_slot("Affiliation", domain, affiliations)
        profile = create_profile("Outcast", person_type, gang_type, price=100)
        add_built_in(profile, first)
        return profile, clan_house, cawdor

    def test_the_second_choice_appears_once_the_first_is_made(self, gang, chained):
        profile, clan_house, _ = chained
        kaustos = hire(gang, profile, "Kaustos", paid=100)
        (first,) = choices_of(kaustos)

        choose(first.anchor.assignment, clan_house)

        assert sorted(slot.kind_label for slot in choices_of(kaustos)) == [
            "Affiliation",
            "House",
        ]

    def test_the_second_is_answered_against_what_gave_it(self, gang, chained):
        profile, clan_house, cawdor = chained
        kaustos = hire(gang, profile, "Kaustos", paid=100)
        (first,) = choices_of(kaustos)
        choose(first.anchor.assignment, clan_house)
        second = next(s for s in choices_of(kaustos) if s.kind_label == "House")

        choose(second.anchor.assignment, cawdor, slot=second.slot)

        second = next(s for s in choices_of(kaustos) if s.kind_label == "House")
        assert second.chosen_name == "House Cawdor"

    def test_un_choosing_the_first_takes_the_whole_chain(self, gang, chained):
        profile, clan_house, cawdor = chained
        kaustos = hire(gang, profile, "Kaustos", paid=100)
        (first,) = choices_of(kaustos)
        choose(first.anchor.assignment, clan_house)
        second = next(s for s in choices_of(kaustos) if s.kind_label == "House")
        choose(second.anchor.assignment, cawdor, slot=second.slot)

        remove(Assignment.objects.get(pickable=clan_house, archived=False))

        assert [slot.kind_label for slot in choices_of(kaustos)] == ["Affiliation"]
        assert not Assignment.objects.filter(pickable=cawdor, archived=False).exists()
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


class TestTheWholeSheetDraws:
    def test_a_gang_with_choices_renders(self, gang, hunter, houses):
        """The sheet is where all of this ends up; a shape it cannot
        draw is a shape nobody sees."""
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        (slot,) = choices_of(kaustos)
        choose(slot.anchor.assignment, houses["Cawdor"])

        sheet = render_gang(gang)

        (drawn,) = sheet.models
        assert [line.chosen for line in drawn.choices] == ["Cawdor"]
        assert_reconciled(gang)


class TestTheScreenBehindTheRow:
    """One route, one page, one click, whether the question came from a
    modifier's offer or from a slot. The pick screen is
    `test_choosing.py`'s subject; what is pinned here is that a slot's
    row has an address at all and that clicking it writes the pick."""

    def slot_line(self, gang):
        from n26.core.views.choose import link_slots

        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        (card,) = sheet.models
        (line,) = card.questions
        return line

    def test_the_row_leads_somewhere(self, gang, hunter, client, owner):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        client.force_login(owner)

        body = client.get(self.slot_line(gang).href).content.decode()

        assert "Cawdor" in body
        assert "Escher" in body
        assert kaustos.name in body

    def test_the_click_settles_the_choice(self, gang, hunter, houses, client, owner):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        client.force_login(owner)
        href = self.slot_line(gang).href

        client.post(href, {"thing": f"library.pickable:{houses['Escher'].pk}"})

        assert choices_of(kaustos)[0].chosen_name == "Escher"
        assert_reconciled(gang)

    def test_clicking_again_changes_the_answer(
        self, gang, hunter, houses, client, owner
    ):
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        client.force_login(owner)
        client.post(
            self.slot_line(gang).href,
            {"thing": f"library.pickable:{houses['Escher'].pk}"},
        )

        client.post(
            self.slot_line(gang).href,
            {"thing": f"library.pickable:{houses['Cawdor'].pk}"},
        )

        (settled,) = choices_of(kaustos)
        assert settled.chosen_name == "Cawdor"
        assert len(settled.picks) == 1
        assert_reconciled(gang)


class TestAPickTheGangHolds:
    """What the gang chose is a fact about everybody in it.

    A choice may say the gang carries the answer. The pick then lands on
    the gang and rides every member's card — including the card of the
    fighter who was asked — so a rule reaching "models with the Mutant
    pick" reaches them. A pick is the only thing the gang holds that
    counts as a member's: its gun is still its own.
    """

    @pytest.fixture
    def domain(self, default_pack):
        return create_slot_type("Archetype", allows_repeats=False)

    @pytest.fixture
    def mutant(self, domain):
        return create_pickable("Mutant", domain)

    @pytest.fixture
    def leader(self, person_type, gang_type, domain, mutant):
        """A profile carrying a choice whose answer the gang holds."""
        picklist = create_picklist("Outcast Archetypes", domain, members=[mutant])
        slot = create_slot("Archetype", domain, picklist, assigned_to="gang")
        profile = create_profile("Outcast Leader", person_type, gang_type, price=120)
        add_built_in(profile, slot)
        return profile

    @pytest.fixture
    def plain(self, person_type, gang_type):
        return create_profile("Scav", person_type, gang_type, price=40)

    def watcher(self, pickable, name="Watcher"):
        """Kit that notices a pick: one rule behind one condition."""
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
        """Only picks widen: a scope asking what this fighter has must
        not find the gang's kit in their hands."""
        from n26.core import select

        boss = hire(gang, leader, "Boss", paid=120)
        arsenal = create_wargear("Gang Mortar")
        assign(arsenal, gang=gang)
        (slot,) = choices_of(boss)
        choose(slot.anchor.assignment, mutant)

        matchable = build_card(boss).model_matchable()

        assert select.Has(mutant).matches(matchable)
        assert not select.Has(arsenal).matches(matchable)

    def test_a_gang_held_option_with_no_choice_behind_it_says_nothing(
        self, gang, leader, mutant
    ):
        """The orphan rule holds wherever the option sits: nobody was
        offered it, so it is not a fact about anybody."""
        from n26.core import select

        boss = hire(gang, leader, "Boss", paid=120)
        assign(mutant, gang=gang)

        assert not select.Has(mutant).matches(build_card(boss).model_matchable())


class TestTwoChoicesOneThingGave:
    """One thing may open two choices of a domain. They share the
    assignment that gave them, so only the slot each pick names keeps
    their answers apart."""

    @pytest.fixture
    def trees(self, default_pack):
        domain = create_slot_type("Skill Tree")
        options = {
            name: create_pickable(name, domain)
            for name in ("Agility", "Brawn", "Cunning")
        }
        picklist = create_picklist("Trees", domain, members=list(options.values()))
        first = create_slot("Tree one", domain, picklist, label="Skill tree 1")
        second = create_slot("Tree two", domain, picklist, label="Skill tree 2")
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
        return charter, options

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
        _, options = trees
        asked = self.asked(venator)

        choose(
            asked["Skill tree 1"].anchor.assignment,
            options["Agility"],
            slot=asked["Skill tree 1"].slot,
        )
        choose(
            asked["Skill tree 2"].anchor.assignment,
            options["Brawn"],
            slot=asked["Skill tree 2"].slot,
        )

        settled = self.asked(venator)
        assert {label: slot.chosen_name for label, slot in settled.items()} == {
            "Skill tree 1": "Agility",
            "Skill tree 2": "Brawn",
        }
        assert [len(slot.picks) for slot in settled.values()] == [1, 1]

    def test_changing_one_leaves_the_other_where_it_was(self, gang, venator, trees):
        _, options = trees
        asked = self.asked(venator)
        for label, option in (("Skill tree 1", "Agility"), ("Skill tree 2", "Brawn")):
            choose(
                asked[label].anchor.assignment,
                options[option],
                slot=asked[label].slot,
            )

        remove(Assignment.objects.get(pickable=options["Agility"], archived=False))
        asked = self.asked(venator)
        choose(
            asked["Skill tree 1"].anchor.assignment,
            options["Cunning"],
            slot=asked["Skill tree 1"].slot,
        )

        settled = self.asked(venator)
        assert {label: slot.chosen_name for label, slot in settled.items()} == {
            "Skill tree 1": "Cunning",
            "Skill tree 2": "Brawn",
        }
        assert_reconciled(gang)

    def test_one_giver_opens_one_choice_per_slot_it_gives(self, venator):
        """Two grants, two rows — not one row per grant per model the
        grant reached."""
        assert sorted(self.asked(venator)) == ["Skill tree 1", "Skill tree 2"]


class TestAChoiceBoughtIntoTheStash:
    """A thing that arrives with its choice settled may be bought
    unassigned. There is no bearer for the pick to land on, and it
    belongs with the item rather than with the gang: it waits in the
    stash beside it and moves when somebody carries the thing."""

    @pytest.fixture
    def banner(self, legacy, legacies, houses):
        gear = create_wargear("Ancestor Banner", price=20)
        slot = create_slot("Banner Legacy", legacy, legacies, label="Gang Legacy")
        add_built_in(gear, slot, default_pickable=houses["Cawdor"])
        return gear

    def test_the_purchase_goes_through(self, gang, banner):
        """The whole buy used to unwind: the pick had no host at all,
        and the constraint that says an assignment has exactly one took
        the purchase down with it."""
        bought = buy(gang.stash, thing=banner, paid=20)

        assert bought.stash == gang.stash
        assert_reconciled(gang)

    def test_the_pick_waits_in_the_stash_beside_it(self, gang, banner, houses):
        buy(gang.stash, thing=banner, paid=20)

        pick = Assignment.objects.get(pickable=houses["Cawdor"], archived=False)
        assert pick.stash == gang.stash
        assert pick.chosen_for_slot is not None
        assert_reconciled(gang)

    def test_the_gang_is_not_handed_the_answer(self, gang, banner, houses):
        """Stashed, not gang-wide: a legacy nobody is carrying yet must
        not reach the roster."""
        buy(gang.stash, thing=banner, paid=20)

        assert Assignment.objects.get(pickable=houses["Cawdor"]).gang is None


class TestWhereAGivenChoiceIsDrawn:
    def test_it_takes_the_place_its_slot_was_given(
        self, gang, person_type, gang_type, legacy, legacies, houses
    ):
        """A choice a modifier handed over sits where the author put it,
        like any other — being given is not a reason to draw last."""
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


class TestTheWordingAListGivesAnOption:
    """A list may call an option something of its own. The wording is
    the list's, so it reaches the picker and stops there: the card
    prints what the thing is called."""

    @pytest.fixture
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

    def test_the_picker_says_what_the_list_calls_it(self, gang, renamed):
        kaustos = hire(gang, renamed, "Kaustos", paid=100)
        _, computed = card_of(kaustos)
        (slot,) = computed.choices

        offer = build_choice_offer(slot, computed)

        assert [option.name for group in offer.groups for option in group.options] == [
            "House of Redemption"
        ]

    def test_the_card_says_the_options_own_name(self, gang, renamed, houses):
        kaustos = hire(gang, renamed, "Kaustos", paid=100)
        (slot,) = choices_of(kaustos)

        choose(slot.anchor.assignment, houses["Cawdor"])

        assert [line.chosen for line in drawn_card(kaustos).choices] == ["Cawdor"]
        assert_reconciled(gang)


def option_key_of(pickable):
    return f"library.pickable:{pickable.pk}"


def button_labels(body):
    """What the page's buttons say, as a reader would read them."""
    import re

    return [
        label.strip()
        for label in re.findall(r"<button[^>]*>(.*?)</button>", body, re.DOTALL)
    ]


def picker_href(gang):
    """Where the one choice on this gang's one fighter is settled."""
    from n26.core.views.choose import link_slots

    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    (card,) = sheet.models
    (line,) = card.questions
    return line.href


class TestAChoiceThatHoldsSeveral:
    """A choice of more than one is worked at rather than answered: each
    option carries its own act, a click settles or unsettles that one,
    and the page comes back. Full, it stops offering the rest — the way
    to something else is to take a pick back, never to have one pushed
    out unasked."""

    @pytest.fixture
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
        client.post(href, {"thing": option_key_of(houses["Cawdor"])})

        landed = client.post(href, {"thing": option_key_of(houses["Escher"])})

        (settled,) = choices_of(wanderer)
        assert sorted(node.name for node in settled.picks) == ["Cawdor", "Escher"]
        # Back to the same choice: the next pick is a click away.
        assert landed["Location"] == href
        assert_reconciled(gang)

    def test_everything_it_holds_draws_as_chosen(self, gang, wanderer, houses, client):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": option_key_of(houses[name])})

        offer = self.offer_for(wanderer)

        assert [
            (option.name, option.is_current, option.control)
            for group in offer.groups
            for option in group.options
        ] == [("Cawdor", True, "remove"), ("Escher", True, "remove")]

    def test_a_full_choice_stops_offering_the_rest(
        self, gang, wanderer, houses, client
    ):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": option_key_of(houses[name])})

        body = client.get(href).content.decode()

        assert "Ironhead Squats" not in body
        assert button_labels(body).count("Remove") == 2

    def test_a_click_on_a_full_choice_writes_nothing(
        self, gang, wanderer, houses, client
    ):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": option_key_of(houses[name])})

        client.post(href, {"thing": option_key_of(houses["Ironhead Squats"])})

        (settled,) = choices_of(wanderer)
        assert sorted(node.name for node in settled.picks) == ["Cawdor", "Escher"]
        assert_reconciled(gang)

    def test_the_control_beside_a_pick_takes_back_that_one(
        self, gang, wanderer, houses, client
    ):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": option_key_of(houses[name])})

        client.post(href, {"remove": option_key_of(houses["Cawdor"])})

        (settled,) = choices_of(wanderer)
        assert [node.name for node in settled.picks] == ["Escher"]
        assert_reconciled(gang)

    def test_taking_one_back_puts_the_rest_on_offer_again(
        self, gang, wanderer, houses, client
    ):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": option_key_of(houses[name])})
        client.post(href, {"remove": option_key_of(houses["Escher"])})

        body = client.get(href).content.decode()

        assert "Ironhead Squats" in body
        assert button_labels(body).count("Choose") == 2

    def test_the_page_ends_with_no_save(self, gang, wanderer, client):
        """Nothing is held back to be saved: every option's own act has
        already been taken or not."""
        said = button_labels(client.get(picker_href(gang)).content.decode())

        assert "Save" not in said
        assert said.count("Choose") == 3

    def test_a_choice_of_one_still_ends_with_save(self, gang, hunter, client, owner):
        """The older shape is untouched: one list, one pick, one act at
        the end of the page."""
        client.force_login(owner)
        hire(gang, hunter, "Kaustos", paid=100)

        said = button_labels(client.get(picker_href(gang)).content.decode())

        assert "Save" in said
        assert "Choose" not in said


class TestAChoiceThatHoldsNone:
    """Nought picks: a choice authored to ask nothing. It offers nothing
    and writes nothing."""

    @pytest.fixture
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

    def test_the_picker_lists_nothing(self, gang, asks_nothing):
        kaustos = hire(gang, asks_nothing, "Kaustos", paid=100)
        _, computed = card_of(kaustos)
        (slot,) = computed.choices

        assert build_choice_offer(slot, computed).is_empty

    def test_a_click_that_reached_it_anyway_writes_nothing(
        self, gang, asks_nothing, houses, client, owner
    ):
        kaustos = hire(gang, asks_nothing, "Kaustos", paid=100)
        client.force_login(owner)

        client.post(picker_href(gang), {"thing": option_key_of(houses["Cawdor"])})

        assert choices_of(kaustos)[0].picks == []
        assert not Assignment.objects.filter(
            pickable__isnull=False, archived=False
        ).exists()


class TestThePickerCostsTheSameHoweverLongTheList:
    def test_the_page_reads_flat_as_the_list_grows(
        self, gang, hunter, legacy, legacies, client, owner, django_assert_num_queries
    ):
        """Six options and twenty-six are the same page read twice: the
        wording is the member's and the identity the option's, and both
        come back with the list."""
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
        """Family is read by more than the menu: the Trading Post sweeps
        every GEAR kind, and a choice on sale would be nonsense."""
        from n26.library.models.assignable import Family

        assert Pickable.family != Family.GEAR
        assert Slot.family != Family.GEAR

    def test_neither_says_its_kind_to_a_player(self, legacy, houses):
        """Internals never leak: the names are authored to be read, the
        kinds are the library's own plumbing."""
        from n26.core.effects import kind_of

        assert kind_of(houses["Cawdor"]) == ""
