"""Slots and picks: a choice made from a curated list.

The shape a new slot type is authored in rather than coded: a
slot type, its pickables, the list they are offered on, and the choice
itself. Gang Legacy is the first use — eight houses, each opening that
house's equipment list to whoever picks it.

What this file holds still is the engine underneath: that assigning a
slot asks the question, that the pick is read off ``chosen_for`` and
nothing is inferred from kinds, that a pickable with no choice behind it
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


# --- Example A: Gang Legacy, eight houses, one choice ----------------------


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def legacy(default_pack):
    """The slot type. Nobody picks two legacies."""
    return create_slot_type(
        "Gang Legacy", plural_name="Gang Legacies", allows_repeats=False
    )


@pytest.fixture
def houses(legacy):
    """Three of the eight, each opening its own equipment list."""
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
        """The narrowing informs and never polices — an owner may hand
        over an off-list pickable of the right slot type."""
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


class TestTwoChoicesOfOneSlotType:
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

    def test_the_card_says_when_one_pickable_answers_both(
        self, gang, twice_asked, houses
    ):
        """The slot type forbids repeats, so picking Cawdor twice is worth
        mentioning — on the model's own card, where the choices are."""
        kaustos = hire(gang, twice_asked, "Kaustos", paid=100)
        for slot in choices_of(kaustos):
            choose(slot.anchor.assignment, houses["Cawdor"])

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
    """Where the slot type takes one pickable once, the picker says which of
    its pickables this holder has already spent elsewhere.

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
            pickable.name: pickable.taken_for
            for group in offer.groups
            for pickable in group.options
        }

    def test_the_pickable_the_other_choice_holds_is_marked(
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
        already drawn as the current pick, which is a different fact."""
        kaustos = hire(gang, twice_asked, "Kaustos", paid=100)
        first, _ = sorted(choices_of(kaustos), key=lambda slot: slot.source)
        choose(first.anchor.assignment, houses["Cawdor"])

        here, _ = self.offers(kaustos)
        (cawdor,) = [
            pickable
            for group in here.groups
            for pickable in group.options
            if pickable.name == "Cawdor"
        ]

        assert (cawdor.taken_for, cawdor.is_current) == ("", True)

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
        # Marked, not locked: the pickable is still a control that works.
        control = re.search(
            rf'<input[^>]*value="library.pickable:{houses["Cawdor"].pk}"[^>]*>', body
        )
        assert control and "disabled" not in control.group()


class TestAnPickableWithNoChoiceBehindIt:
    """A pickable an owner hands over with no slot to answer shows
    nothing and does nothing — not a line, not a modifier, not a fact
    another rule can match on."""

    @pytest.fixture
    def loud(self, legacy, default_pack):
        """A pickable that would be impossible to miss if it ran."""
        pickable = create_pickable("Cawdor", legacy)
        modifier(
            "Cawdor: a rule",
            targets_model(),
            ef_adds(create_rule("House Cawdor")),
            carried_by=pickable,
        )
        return pickable

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

    def test_a_hand_made_pick_draws_no_line_either(
        self, gang, bundled, houses, legacy, legacies
    ):
        """Answered outright rather than by a starting pick, which is
        the other way into a hidden choice. Hidden means the card says
        nothing, however the answer arrived — so the pick draws no line
        of its own, and its holder shows only what it gives."""
        from n26.core.models import Assignment
        from n26.library.models import Slot

        kaustos = hire(gang, bundled, "Kaustos", paid=100)
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
    """A slot the gang holds is asked once, on the gang's own card. It
    rides every member's card so its behaviour reaches them; the
    question is the gang's."""

    @pytest.fixture
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

    The pick is gang-hosted and its payload says all models — scoped, so
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


class TestAGangPickOpensAChoiceOnEveryModel:
    """The Water Guild shape: the gang's pick grants a slot to all
    models, so each fighter's card asks its own Guild Role — anchored on
    the gang's pick riding their card. The gang's own card is never
    asked: the grant reaches no model there."""

    @pytest.fixture
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
        # Founded after the built-in exists: founding is what writes the
        # gang's Alliance slot.
        return found_gang("The Long Hunt", gang_type, owner=owner, budget=1000)

    def crew_with_the_pick(self, gang, profile, guild):
        fighters = [
            hire(gang, profile, name, paid=100) for name in ("Kaustos", "Grendel")
        ]
        (alliance_row,) = gang_choices(gang).choices
        choose(alliance_row.anchor.assignment, guild)
        return fighters

    def test_every_model_is_asked_and_the_gang_is_not(self, gang, guild_shape):
        profile, guild, _, _ = guild_shape
        fighters = self.crew_with_the_pick(gang, profile, guild)

        for fighter in fighters:
            assert [row.kind_label for row in choices_of(fighter)] == ["Guild Role"]
        assert [row.kind_label for row in gang_choices(gang).choices] == ["Alliance"]
        assert_reconciled(gang)

    def test_the_role_settles_per_fighter_and_its_payload_lands(
        self, gang, guild_shape
    ):
        profile, guild, nauticus, role_slot = guild_shape
        kaustos, grendel = self.crew_with_the_pick(gang, profile, guild)
        (role_row,) = choices_of(kaustos)

        choose(role_row.anchor.assignment, nauticus, slot=role_slot, miniature=kaustos)

        _, computed = card_of(kaustos)
        assert [line.name for line in computed.rules] == ["Master of Water"]
        assert card_of(grendel)[1].rules == []
        assert Assignment.objects.get(pickable=nauticus).miniature == kaustos
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

    def test_unchoosing_the_alliance_takes_every_role_with_it(self, gang, guild_shape):
        profile, guild, nauticus, role_slot = guild_shape
        kaustos, _ = self.crew_with_the_pick(gang, profile, guild)
        (role_row,) = choices_of(kaustos)
        choose(role_row.anchor.assignment, nauticus, slot=role_slot, miniature=kaustos)

        remove(Assignment.objects.get(pickable=guild))

        assert choices_of(kaustos) == []
        assert not Assignment.objects.filter(
            pickable__isnull=False, archived=False
        ).exists()
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
    """The giver need not be a line the card holds. A wargear gives a
    hidden carrier and the carrier opens the choice: nothing wrote the
    carrier down, so the choice is addressed on the wargear the whole
    chain stands on, and goes when the wargear does.
    """

    @pytest.fixture
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

    def test_the_choice_is_asked_and_addressed_on_the_wargear(self, gang, relic):
        profile, wargear, _, _ = relic
        kaustos = hire(gang, profile, "Kaustos", paid=100)
        bought = buy(kaustos, thing=wargear, paid=30)

        (rite_row,) = choices_of(kaustos)

        assert rite_row.kind_label == "Rite"
        assert rite_row.anchor.assignment == bought
        assert_reconciled(gang)

    def test_what_is_picked_lands_and_giving_the_wargear_back_takes_it(
        self, gang, relic
    ):
        profile, wargear, vigil, rite_slot = relic
        kaustos = hire(gang, profile, "Kaustos", paid=100)
        bought = buy(kaustos, thing=wargear, paid=30)
        (rite_row,) = choices_of(kaustos)
        choose(rite_row.anchor.assignment, vigil, slot=rite_slot)
        assert [line.name for line in card_of(kaustos)[1].rules] == ["Keeps the Vigil"]

        refund(bought)

        assert choices_of(kaustos) == []
        assert not Assignment.objects.filter(pickable=vigil, archived=False).exists()
        # The refund repinned the gang it reached through the assignment,
        # which is not this instance.
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestAGangGuestOpensAChoiceOnEveryModel:
    """The same shape one hop further down the chain: what opens the
    choice is not a line the gang holds but a rule the gang was *given* —
    an alliance's, written nowhere. The choice is asked on every fighter
    all the same, addressed on the line the chain of grants stands on,
    which is the alliance the gang signed.

    A player who signed the alliance saw its rule arrive on the gang and
    the Guild Role it opens arrive on nobody: every fighter had the role's
    behaviour waiting and no card ever asked which role.
    """

    @pytest.fixture
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
        # What the gang is given, and what it opens. The rule is held by
        # grant: no assignment names it anywhere.
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

    def test_the_gang_holds_the_rule_by_grant_and_nothing_writes_it_down(
        self, gang, guild_shape
    ):
        profile, alliance, _, _ = guild_shape
        (kaustos, _), _ = self.crew_and_alliance(gang, profile, alliance)

        _, computed = card_of(kaustos)
        assert [guest.name for guest in computed.echoed] == ["The Water Pact"]
        assert not Assignment.objects.filter(
            rule__isnull=False, gang_root=gang
        ).exists()
        assert_reconciled(gang)

    def test_every_model_is_asked_and_the_gang_is_not(self, gang, guild_shape):
        profile, alliance, _, _ = guild_shape
        fighters, _ = self.crew_and_alliance(gang, profile, alliance)

        for fighter in fighters:
            assert [row.kind_label for row in choices_of(fighter)] == ["Guild Role"]
        assert [row.kind_label for row in gang_choices(gang).choices] == []
        assert_reconciled(gang)

    def test_the_choice_names_the_rule_and_is_asked_on_the_alliance(
        self, gang, guild_shape
    ):
        profile, alliance, _, _ = guild_shape
        (kaustos, _), signed = self.crew_and_alliance(gang, profile, alliance)

        (role_row,) = choices_of(kaustos)

        # The player is told what opened the choice; the address behind it
        # is the written line that stands under the whole chain.
        assert role_row.source == "The Water Pact"
        assert role_row.anchor.assignment == signed
        assert_reconciled(gang)

    def test_the_role_settles_per_fighter_and_its_payload_lands(
        self, gang, guild_shape
    ):
        profile, alliance, nauticus, role_slot = guild_shape
        (kaustos, grendel), _ = self.crew_and_alliance(gang, profile, alliance)
        (role_row,) = choices_of(kaustos)

        choose(role_row.anchor.assignment, nauticus, slot=role_slot, miniature=kaustos)

        # The guest itself draws no line on a fighter: what the pick gives
        # is the fighter's, and the rule behind it stays the gang's.
        assert [line.name for line in card_of(kaustos)[1].rules] == ["Master of Water"]
        assert card_of(grendel)[1].rules == []
        assert Assignment.objects.get(pickable=nauticus).miniature == kaustos
        assert_reconciled(gang)

    def test_dropping_the_alliance_takes_every_role_with_it(self, gang, guild_shape):
        profile, alliance, nauticus, role_slot = guild_shape
        (kaustos, _), signed = self.crew_and_alliance(gang, profile, alliance)
        (role_row,) = choices_of(kaustos)
        choose(role_row.anchor.assignment, nauticus, slot=role_slot, miniature=kaustos)

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

    def test_clicking_again_changes_the_pick(self, gang, hunter, houses, client, owner):
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


class TestAnOptionalChoiceOffersNone:
    """A choice expecting no picks ends its list with a None row, which
    takes the standing pick back and leaves the choice open. A choice
    that expects one offers no such row — leaving it open is already
    free, and there is nothing None would say."""

    @pytest.fixture
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

    def test_the_list_ends_with_a_none_row(self, gang, optional_hunter, client, owner):
        hire(gang, optional_hunter, "Kaustos", paid=100)
        client.force_login(owner)

        body = client.get(self.slot_line(gang).href).content.decode()

        assert 'value="none"' in body
        assert "None" in body

    def test_a_required_choice_offers_no_none(self, gang, hunter, client, owner):
        hire(gang, hunter, "Kaustos", paid=100)
        client.force_login(owner)

        assert (
            'value="none"' not in client.get(self.slot_line(gang).href).content.decode()
        )

    def test_clicking_none_takes_the_pick_back(
        self, gang, optional_hunter, houses, client, owner
    ):
        kaustos = hire(gang, optional_hunter, "Kaustos", paid=100)
        client.force_login(owner)
        href = self.slot_line(gang).href
        client.post(href, {"thing": f"library.pickable:{houses['Escher'].pk}"})

        response = client.post(href, {"thing": "none"})

        assert response.status_code == 302
        (line,) = choices_of(kaustos)
        assert line.chosen_name is None
        assert not Assignment.objects.filter(
            pickable__isnull=False, archived=False
        ).exists()
        assert_reconciled(gang)

    def test_none_with_nothing_standing_settles_quietly(
        self, gang, optional_hunter, client, owner
    ):
        kaustos = hire(gang, optional_hunter, "Kaustos", paid=100)
        client.force_login(owner)

        response = client.post(self.slot_line(gang).href, {"thing": "none"})

        assert response.status_code == 302
        (line,) = choices_of(kaustos)
        assert line.chosen_name is None
        assert_reconciled(gang)

    def test_a_post_cannot_reset_a_required_choice(
        self, gang, hunter, houses, client, owner
    ):
        """The page did not draw the row, so a hand-built post is a
        stale click, and the pick stands."""
        kaustos = hire(gang, hunter, "Kaustos", paid=100)
        client.force_login(owner)
        href = self.slot_line(gang).href
        client.post(href, {"thing": f"library.pickable:{houses['Escher'].pk}"})

        response = client.post(href, {"thing": "none"})

        assert response.status_code == 302
        assert response.headers["Location"] == href
        (line,) = choices_of(kaustos)
        assert line.chosen_name == "Escher"

    def test_a_choice_worked_at_a_pick_at_a_time_has_no_none_row(
        self, gang, person_type, gang_type, legacy, legacies, client, owner
    ):
        """Each pick already carries its own Remove, which is the reset."""
        slot = create_slot("Two legacies", legacy, legacies, min_picks=0, max_picks=2)
        profile = create_profile("Wanderer", person_type, gang_type, price=100)
        add_built_in(profile, slot)
        hire(gang, profile, "Kaustos", paid=100)
        client.force_login(owner)

        assert (
            'value="none"' not in client.get(self.slot_line(gang).href).content.decode()
        )


class TestAPickTheGangHolds:
    """What the gang chose is a fact about everybody in it.

    A choice may say the gang carries the answer. The pick then lands on
    the gang and rides every member's card — including the card of the
    fighter who was asked — so a rule reaching "models with the Mutant
    pick" reaches them. A pick is the only thing the gang holds that
    counts as a member's: its gun is still its own.
    """

    @pytest.fixture
    def slot_type(self, default_pack):
        return create_slot_type("Archetype", allows_repeats=False)

    @pytest.fixture
    def mutant(self, slot_type):
        return create_pickable("Mutant", slot_type)

    @pytest.fixture
    def leader(self, person_type, gang_type, slot_type, mutant):
        """A profile carrying a choice whose answer the gang holds."""
        picklist = create_picklist("Outcast Archetypes", slot_type, members=[mutant])
        slot = create_slot("Archetype", slot_type, picklist, assigned_to="gang")
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

    def test_a_gang_held_pickable_with_no_choice_behind_it_says_nothing(
        self, gang, leader, mutant
    ):
        """The orphan rule holds wherever the pickable sits: nobody was
        offered it, so it is not a fact about anybody."""
        from n26.core import select

        boss = hire(gang, leader, "Boss", paid=120)
        assign(mutant, gang=gang)

        assert not select.Has(mutant).matches(build_card(boss).model_matchable())


class TestTwoChoicesOneThingGave:
    """One thing may open two choices of a slot type. They share the
    assignment that gave them, so only the slot each pick names keeps
    their answers apart."""

    @pytest.fixture
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

    def test_changing_one_leaves_the_other_where_it_was(self, gang, venator, trees):
        _, pickables = trees
        asked = self.asked(venator)
        for label, pickable in (("Skill tree 1", "Agility"), ("Skill tree 2", "Brawn")):
            choose(
                asked[label].anchor.assignment,
                pickables[pickable],
                slot=asked[label].slot,
            )

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


class TestTheWordingAListGivesAnPickable:
    """A list may call a pickable something of its own. The wording is
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

        assert [
            pickable.name for group in offer.groups for pickable in group.options
        ] == ["House of Redemption"]

    def test_the_card_says_the_pickables_own_name(self, gang, renamed, houses):
        kaustos = hire(gang, renamed, "Kaustos", paid=100)
        (slot,) = choices_of(kaustos)

        choose(slot.anchor.assignment, houses["Cawdor"])

        assert [line.chosen for line in drawn_card(kaustos).choices] == ["Cawdor"]
        assert_reconciled(gang)


def pickable_key_of(pickable):
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
    """A choice of more than one is worked at rather than made in one stroke: each
    pickable carries its own act, a click settles or unsettles that one,
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
        client.post(href, {"thing": pickable_key_of(houses["Cawdor"])})

        landed = client.post(href, {"thing": pickable_key_of(houses["Escher"])})

        (settled,) = choices_of(wanderer)
        assert sorted(node.name for node in settled.picks) == ["Cawdor", "Escher"]
        # Back to the same choice: the next pick is a click away.
        assert landed["Location"] == href
        assert_reconciled(gang)

    def test_everything_it_holds_draws_as_chosen(self, gang, wanderer, houses, client):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": pickable_key_of(houses[name])})

        offer = self.offer_for(wanderer)

        assert [
            (pickable.name, pickable.is_current, pickable.control)
            for group in offer.groups
            for pickable in group.options
        ] == [("Cawdor", True, "remove"), ("Escher", True, "remove")]
        assert_reconciled(gang)

    def test_a_full_choice_stops_offering_the_rest(
        self, gang, wanderer, houses, client
    ):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": pickable_key_of(houses[name])})

        body = client.get(href).content.decode()

        assert "Ironhead Squats" not in body
        assert button_labels(body).count("Remove") == 2
        assert_reconciled(gang)

    def test_a_click_on_a_full_choice_writes_nothing(
        self, gang, wanderer, houses, client
    ):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": pickable_key_of(houses[name])})

        client.post(href, {"thing": pickable_key_of(houses["Ironhead Squats"])})

        (settled,) = choices_of(wanderer)
        assert sorted(node.name for node in settled.picks) == ["Cawdor", "Escher"]
        assert_reconciled(gang)

    def test_the_control_beside_a_pick_takes_back_that_one(
        self, gang, wanderer, houses, client
    ):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": pickable_key_of(houses[name])})

        client.post(href, {"remove": pickable_key_of(houses["Cawdor"])})

        (settled,) = choices_of(wanderer)
        assert [node.name for node in settled.picks] == ["Escher"]
        assert_reconciled(gang)

    def test_taking_one_back_puts_the_rest_on_offer_again(
        self, gang, wanderer, houses, client
    ):
        href = picker_href(gang)
        for name in ("Cawdor", "Escher"):
            client.post(href, {"thing": pickable_key_of(houses[name])})
        client.post(href, {"remove": pickable_key_of(houses["Escher"])})

        body = client.get(href).content.decode()

        assert "Ironhead Squats" in body
        assert button_labels(body).count("Add") == 2
        assert_reconciled(gang)

    def test_the_page_ends_with_no_save(self, gang, wanderer, client):
        """Nothing is held back to be saved: every pickable's own act has
        already been taken or not."""
        said = button_labels(client.get(picker_href(gang)).content.decode())

        assert "Save" not in said
        assert said.count("Add") == 3
        assert_reconciled(gang)

    def test_a_choice_of_one_still_ends_with_save(self, gang, hunter, client, owner):
        """The older shape is untouched: one list, one pick, one act at
        the end of the page."""
        client.force_login(owner)
        hire(gang, hunter, "Kaustos", paid=100)

        said = button_labels(client.get(picker_href(gang)).content.decode())

        assert "Save" in said
        # Neither verb: a one-pick picker draws radios and a Save, and a
        # per-option button under either word would mean it was drawn as
        # the several-pick list by mistake.
        assert "Add" not in said and "Choose" not in said
        assert_reconciled(gang)


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
        assert_reconciled(gang)

    def test_a_click_that_reached_it_anyway_writes_nothing(
        self, gang, asks_nothing, houses, client, owner
    ):
        kaustos = hire(gang, asks_nothing, "Kaustos", paid=100)
        client.force_login(owner)

        client.post(picker_href(gang), {"thing": pickable_key_of(houses["Cawdor"])})

        assert choices_of(kaustos)[0].picks == []
        assert not Assignment.objects.filter(
            pickable__isnull=False, archived=False
        ).exists()
        assert_reconciled(gang)

    def test_the_card_draws_the_row_and_no_way_in(
        self, gang, asks_nothing, client, owner
    ):
        """The row still stands, headed as authored, but nothing on it
        is clickable: a choice that asks nothing is full from the start,
        and a link there would lead to a picker with nothing on it."""
        from django.urls import reverse

        hire(gang, asks_nothing, "Kaustos", paid=100)
        client.force_login(owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        row = body[body.index("Gang Legacy</dt>") :]
        row = row[: row.index("</dd>")]
        assert ">Choose</" not in row
        assert ">Add</" not in row


class TestARollTableInThePicker:
    """A player who rolled on the physical table finds their result by
    the roll: the picker leads each option with its band and lists them
    in roll order. An ordinary list draws exactly as it always has."""

    @pytest.fixture
    def injury(self, default_pack):
        return create_slot_type("Lasting Injury", allows_repeats=True)

    @pytest.fixture
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

    def test_each_option_carries_its_band_in_roll_order(self, yolanda):
        offer = self.offer_for(yolanda)
        rows = [(o.band, o.name) for g in offer.groups for o in g.options]
        assert rows == [
            ("11", "Lesson Learnt"),
            ("21-26", "Out Cold"),
            ("51", "Eye Injury"),
        ]

    def test_an_ordinary_list_carries_no_bands(self, gang, hunter, houses):
        sev = hire(gang, hunter, "Sev", paid=100)
        _, computed = card_of(sev)
        offer = build_choice_offer(next(iter(choices_of(sev))), computed)
        assert all(o.band == "" for g in offer.groups for o in g.options)

    def test_the_page_leads_each_row_with_the_band(self, client, owner, gang, yolanda):

        from n26.core.views.choose import link_slots

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


class TestThePickerStaysFlatHoweverLongTheList:
    def test_the_page_reads_flat_as_the_list_grows(
        self, gang, hunter, legacy, legacies, client, owner, django_assert_num_queries
    ):
        """Six pickables and twenty-six are the same page read twice: the
        wording is the member's and the identity the pickable's, and both
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


# --- Example B: a choice worked at a pick at a time, allowing repeats ------


class TestAChoiceThatAllowsRepeats:
    """A standing choice that holds several picks and may hold the same
    one twice — the shape a lasting injury takes: a fighter carries the
    slot from hire, and a second Eye Injury is a second Eye Injury.

    Nothing here is a new kind. The slot type says it allows repeats,
    the slot says how many it holds, and the card and the picker draw
    what those two already mean.
    """

    @pytest.fixture
    def injury(self, default_pack):
        return create_slot_type(
            "Lasting Injury", plural_name="Lasting Injuries", allows_repeats=True
        )

    @pytest.fixture
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
    def injuries(self, injury, results):
        return create_picklist(
            "Lasting Injury Table", injury, members=list(results.values())
        )

    @pytest.fixture
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

    def test_it_arrives_open_under_its_own_label(self, yolanda):
        line = self._line(yolanda)
        assert not line.is_resolved
        assert not line.is_full

    def test_the_same_result_twice_stands_twice(self, yolanda, results):
        self._pick(yolanda, results["Eye Injury"])
        self._pick(yolanda, results["Eye Injury"])

        picks = [p.assignable for p in self._slot(yolanda).picks]
        assert picks == [results["Eye Injury"]] * 2
        assert self._line(yolanda).chosen == "Eye Injury, Eye Injury"

    def test_and_what_it_does_is_done_twice(self, yolanda, results):
        self._pick(yolanda, results["Eye Injury"])
        self._pick(yolanda, results["Eye Injury"])

        _, computed = card_of(yolanda)
        from_eye = [c for c in computed.stat_changes if c.source == "Eye Injury"]
        assert len(from_eye) == 2

    def test_the_card_keeps_asking_until_it_is_full(self, yolanda, results):
        self._pick(yolanda, results["Out Cold"])
        line = self._line(yolanda)
        assert line.is_resolved and not line.is_full

        self._pick(yolanda, results["Eye Injury"])
        self._pick(yolanda, results["Eye Injury"])
        assert self._line(yolanda).is_full

    def test_a_choice_that_holds_one_is_full_once_chosen(self, gang, hunter, houses):
        """The one-pick shape is unchanged: chosen is full, so the card
        stops asking exactly when it did before."""
        sev = hire(gang, hunter, "Sev", paid=100)
        assert not next(iter(drawn_card(sev).choices)).is_full

        choose(next(iter(choices_of(sev))).anchor.assignment, houses["Cawdor"])
        line = next(iter(drawn_card(sev).choices))
        assert line.is_resolved and line.is_full

    def test_the_picker_offers_a_held_result_again(self, yolanda, results):
        self._pick(yolanda, results["Eye Injury"])

        _, computed = card_of(yolanda)
        offer = build_choice_offer(self._slot(yolanda), computed)
        held = next(
            o for g in offer.groups for o in g.options if o.name == "Eye Injury"
        )
        assert held.is_current
        assert held.control == "both"

    def test_where_repeats_are_not_allowed_a_held_pick_is_only_removable(
        self, gang, person_type, gang_type, legacy, houses
    ):
        """The same picker under the other doctrine: a several-pick
        choice of a type that forbids repeats offers a held pick only its
        way back."""
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

    def test_removing_the_slot_takes_every_pick_and_its_effects(self, yolanda, results):
        self._pick(yolanda, results["Eye Injury"])
        self._pick(yolanda, results["Eye Injury"])
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


class TestAChoiceThatAllowsRepeatsOnScreen:
    """The same choice through the pages: the picker takes a second
    click on a held result as a second pick, and the card keeps its
    Choose beside what is already held until the choice is full."""

    @pytest.fixture
    def injury(self, default_pack):
        return create_slot_type(
            "Lasting Injury", plural_name="Lasting Injuries", allows_repeats=True
        )

    @pytest.fixture
    def results(self, injury):
        return {
            name: create_pickable(name, injury) for name in ("Eye Injury", "Out Cold")
        }

    @pytest.fixture
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
        href, _ = self._href(gang)
        eye = results["Eye Injury"]

        assert self._post(client, href, eye).status_code == 302
        assert self._post(client, href, eye).status_code == 302

        assert Assignment.objects.filter(pickable=eye, archived=False).count() == 2
        assert_reconciled(gang)

    def test_the_picker_draws_both_controls_on_a_held_result(
        self, client, owner, gang, yolanda, results
    ):
        client.force_login(owner)
        href, _ = self._href(gang)
        self._post(client, href, results["Eye Injury"])

        body = client.get(href).content.decode()
        assert 'aria-label="Remove Eye Injury"' in body
        assert 'aria-label="Add Eye Injury again"' in body
        # The result not yet held offers only the one way in.
        assert 'aria-label="Add Out Cold"' in body
        assert 'aria-label="Remove Out Cold"' not in body

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
        assert ">Add</" in row[: row.index("</dd>")]

    def test_and_stops_asking_once_full(self, client, owner, gang, yolanda, results):
        client.force_login(owner)
        href, sheet_url = self._href(gang)
        self._post(client, href, results["Eye Injury"])
        self._post(client, href, results["Eye Injury"])

        body = client.get(sheet_url).content.decode()
        # The row, not the flash message that also names the choice.
        row = body[body.index("Lasting Injuries</dt>") :]
        assert "Eye Injury, Eye Injury" in row
        assert ">Add</" not in row[: row.index("</dd>")]

    def test_the_confirmation_uses_the_verb_the_button_did(
        self, client, owner, gang, yolanda, results
    ):
        from django.contrib.messages import get_messages

        client.force_login(owner)
        href, _ = self._href(gang)
        response = self._post(client, href, results["Eye Injury"])

        said = [str(m) for m in get_messages(response.wsgi_request)]
        assert any(m.startswith("Added Eye Injury") for m in said), said

    def test_a_third_click_on_a_full_choice_is_refused_in_words(
        self, client, owner, gang, yolanda, results
    ):
        client.force_login(owner)
        href, _ = self._href(gang)
        eye = results["Eye Injury"]
        self._post(client, href, eye)
        self._post(client, href, eye)

        response = self._post(client, href, eye)
        assert response.status_code == 302
        assert Assignment.objects.filter(pickable=eye, archived=False).count() == 2
        from django.contrib.messages import get_messages

        said = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("holds all the picks" in m for m in said)

    def test_the_sheet_reads_flat_however_many_are_hurt(
        self, client, owner, gang, ganger, yolanda, results
    ):
        """Whether a choice is full is read off picks the card already
        holds, so a sheet of injured fighters costs what a sheet of
        unhurt ones does."""
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
