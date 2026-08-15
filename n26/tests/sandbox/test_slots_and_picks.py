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
from n26.core.render import build_model_card, render_gang
from n26.library.authoring import targets_model as targets_model_with
from n26.library.models import Pickable, Slot
from n26.tests.sandbox.actions import (
    add_built_in,
    assign,
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
