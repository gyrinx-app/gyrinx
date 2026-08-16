"""The Archetype shape: two choices over one slot type, reaching differently.

The third example of the slots-and-picks design. One slot type, used twice:

* the leader is offered a choice whose pick belongs to the **gang**, and
  whose payload reaches every model *except* Champions — the spoken
  negation the condition grammar carries;
* a champion is offered a choice of the same slot type whose pick is his
  own, and reaches nobody else.

Sandbox content shaped like a gang list that works this way. Which
archetypes the edition offers, which of them a champion may take, and
what each one does are the maintainer's to state; the shape is what is
proved here.

The library is built with the authoring verbs — the authoring pages are
``test_gang_legacy.py``'s walkthrough — and the playing goes through the
real pages.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_choice_offer, render_gang
from n26.core.views.choose import link_slots
from n26.library.authoring import (
    add_built_in,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
    create_subtype,
    ef_adds,
    has_subtypes,
    modifier,
    targets_every_model,
    targets_model,
)
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


#: What the leader's choice offers, and what the champion's does. One
#: pickable is on both lists, which is what makes taking it twice a thing
#: anybody could do.
GANG_ARCHETYPES = ("Mutant", "Renegade")
CHAMPION_ARCHETYPES = ("Mutant", "Duellist")

#: The ranks, and what each is hired at.
RANKS = (
    ("Outcast Leader", 120),
    ("Outcast Champion", 90),
    ("Outcast Ganger", 50),
)

#: What the gang's archetype gives, to everyone the condition does not
#: rule out, and what a champion's own gives to him alone.
GANG_PAYLOAD = "Unstable"
CHAMPION_PAYLOAD = "Duellist's Poise"

#: The rank the gang-wide payload steps around. Named as an exception
#: rather than by listing everyone else, so a rank added later is
#: reached without anyone revisiting the condition.
EXCEPTED = "Outcast Champion"


@pytest.fixture
def owner(db):
    return User.objects.create_user("archetype-player")


@pytest.fixture
def ranks(default_pack):
    return {name: create_subtype(name) for name, _ in RANKS}


@pytest.fixture
def slot_type(default_pack):
    """One slot type for both choices. Nobody takes an archetype twice."""
    return create_slot_type("Archetype", allows_repeats=False)


@pytest.fixture
def archetypes(slot_type, ranks):
    """The pickables of the slot type, and what two of them do.

    The gang's Mutant reaches every model except Champions; the
    champion's Duellist reaches whoever picked it and nobody else.
    """
    made = {
        name: create_pickable(name, slot_type)
        for name in dict.fromkeys(GANG_ARCHETYPES + CHAMPION_ARCHETYPES)
    }
    modifier(
        f"Mutant: {GANG_PAYLOAD}",
        targets_every_model(has_subtypes(ranks[EXCEPTED], negate=True)),
        ef_adds(create_rule(GANG_PAYLOAD)),
        attach_to=made["Mutant"],
    )
    modifier(
        f"Duellist: {CHAMPION_PAYLOAD}",
        targets_model(),
        ef_adds(create_rule(CHAMPION_PAYLOAD)),
        attach_to=made["Duellist"],
    )
    return made


@pytest.fixture
def gang_choice(slot_type, archetypes):
    """Offered to the leader, answered by the gang."""
    return create_slot(
        "Gang archetype",
        slot_type,
        create_picklist(
            "Outcast Archetypes",
            slot_type,
            members=[archetypes[name] for name in GANG_ARCHETYPES],
        ),
        label="Archetype",
        min_picks=1,
        max_picks=1,
        assigned_to="gang",
    )


@pytest.fixture
def champion_choice(slot_type, archetypes):
    """Offered to a champion, and his own."""
    return create_slot(
        "Champion archetype",
        slot_type,
        create_picklist(
            "Champion Archetypes",
            slot_type,
            members=[archetypes[name] for name in CHAMPION_ARCHETYPES],
        ),
        label="Archetype",
        min_picks=1,
        max_picks=1,
        assigned_to="bearer",
    )


@pytest.fixture
def profiles(person_type, gang_type, ranks, gang_choice, champion_choice):
    """One profile per rank, the leader carrying the gang's choice and
    the champion carrying his own."""
    made = {}
    for name, price in RANKS:
        profile = create_profile(name, person_type, gang_type, price=price)
        add_built_in(profile, ranks[name])
        made[name] = profile
    add_built_in(made["Outcast Leader"], gang_choice)
    add_built_in(made[EXCEPTED], champion_choice)
    return made


@pytest.fixture
def gang(owner, gang_type):
    return found_gang("The Unmade", gang_type, owner=owner, budget=1000)


@pytest.fixture
def crew(gang, profiles):
    return {name: hire(gang, profiles[name], name, paid=price) for name, price in RANKS}


@pytest.fixture
def reader(client, owner):
    client.force_login(owner)
    return client


def sheet_of(gang):
    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    return sheet


def card_of(gang, name):
    return next(card for card in sheet_of(gang).models if card.name == name)


def picker_url(gang, name):
    (line,) = card_of(gang, name).questions
    return line.href


def choose(reader, gang, name, pickable):
    return reader.post(
        picker_url(gang, name), {"thing": f"library.pickable:{pickable.pk}"}
    )


def computed_card(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def rules_on(miniature):
    return [line.name for line in computed_card(miniature).rules]


def offer_for(miniature):
    """The picker for this model's own choice, as the page builds it."""
    computed = computed_card(miniature)
    (slot,) = computed.choices
    return build_choice_offer(slot, computed)


class TestTheLeaderIsAskedAndTheGangAnswers:
    """A slot built into the leader's profile and assigned to the gang:
    the choice row is drawn where the slot sits, and the pick lands
    where the slot says."""

    def test_the_choice_row_is_on_the_leaders_card(self, reader, gang, crew):
        (line,) = card_of(gang, "Outcast Leader").questions

        assert line.kind_label == "Archetype"
        assert line.chosen is None

    def test_the_gangs_own_card_does_not_draw_it(self, reader, gang, crew):
        """Where a slot is drawn is where it is assigned. The gang
        answers this one; the gang was not the one asked."""
        assert sheet_of(gang).questions == []

    def test_the_ganger_is_not_asked_at_all(self, reader, gang, crew):
        assert card_of(gang, "Outcast Ganger").questions == []

    def test_the_gang_page_draws_the_control_on_his_card(self, reader, gang, crew):
        body = reader.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert picker_url(gang, "Outcast Leader") in body

    def test_what_he_picks_belongs_to_the_gang(self, reader, gang, crew, archetypes):
        response = choose(reader, gang, "Outcast Leader", archetypes["Mutant"])

        assert response.status_code == 302
        pick = Assignment.objects.get(pickable=archetypes["Mutant"])
        assert (pick.gang, pick.miniature) == (gang, None)
        assert card_of(gang, "Outcast Leader").questions[0].chosen == "Mutant"
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestReachingEveryoneExceptOneRank:
    """The payload is scoped by saying who it steps around. Everyone the
    condition does not name is reached, so a rank hired afterwards is
    reached too — which is the difference between an exception and a
    list of everybody else."""

    @pytest.fixture
    def mutant(self, reader, gang, crew, archetypes):
        choose(reader, gang, "Outcast Leader", archetypes["Mutant"])
        return crew

    def test_the_leader_and_the_ganger_are_reached(self, mutant):
        assert GANG_PAYLOAD in rules_on(mutant["Outcast Leader"])
        assert GANG_PAYLOAD in rules_on(mutant["Outcast Ganger"])

    def test_the_champion_is_untouched(self, mutant):
        assert rules_on(mutant[EXCEPTED]) == []

    def test_a_rank_that_did_not_exist_yet_is_reached_too(
        self, reader, gang, mutant, person_type, default_pack
    ):
        """The condition names one rank, so nothing has to be revisited
        when another is authored."""
        later = create_profile("Hive Scum", person_type, gang.gang_type, price=20)
        add_built_in(later, create_subtype("Hive Scum"))
        scum = hire(gang, later, "Scum", paid=20)

        assert GANG_PAYLOAD in rules_on(scum)
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_no_card_draws_a_line_for_the_gangs_pick(self, reader, gang, mutant):
        """It reaches every model and is listed on none of them: what
        the gang holds is said on the gang."""
        for card in sheet_of(gang).models:
            assert [line.name for line in card.equipment] == []


class TestTheChampionsOwnChoice:
    """The same slot type, a personal reach: his card asks, his card
    answers, and nobody else is touched."""

    def test_his_card_asks_it(self, reader, gang, crew):
        (line,) = card_of(gang, EXCEPTED).questions

        assert line.kind_label == "Archetype"

    def test_his_picker_offers_his_own_list(self, reader, gang, crew, archetypes):
        body = reader.get(picker_url(gang, EXCEPTED)).content.decode()

        for name in CHAMPION_ARCHETYPES:
            assert f"library.pickable:{archetypes[name].pk}" in body, name
        assert f"library.pickable:{archetypes['Renegade'].pk}" not in body

    def test_the_pick_is_his(self, reader, gang, crew, archetypes):
        choose(reader, gang, EXCEPTED, archetypes["Duellist"])

        pick = Assignment.objects.get(pickable=archetypes["Duellist"])
        assert pick.miniature == crew[EXCEPTED]
        assert pick.gang is None

    def test_what_it_gives_reaches_him_alone(self, reader, gang, crew, archetypes):
        choose(reader, gang, EXCEPTED, archetypes["Duellist"])

        assert rules_on(crew[EXCEPTED]) == [CHAMPION_PAYLOAD]
        assert rules_on(crew["Outcast Ganger"]) == []
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestTwoChoicesOfOneSlotTypeOnTwoHolders:
    """Both choices are of a slot type that refuses repeats, and they sit on
    two different holders — the gang and the champion.

    What a slot type refusing repeats buys is what one holder says about
    itself: its picker marks the pickables it has already spent on another
    of its own choices, and its card notes the same pickable answering two
    of them. Neither is said here, because there is no holder holding
    both: one pick is the gang's and the other is the champion's.
    Marking across holders would be a different rule, and a mark would
    have no other choice of this holder's to name.

    What one holder holding two of them says is
    ``test_slots_and_picks.py``'s.
    """

    @pytest.fixture
    def settled(self, reader, gang, crew, archetypes):
        choose(reader, gang, "Outcast Leader", archetypes["Mutant"])
        return crew

    def test_settling_one_leaves_the_other_open(self, reader, gang, settled):
        assert card_of(gang, EXCEPTED).questions[0].chosen is None

    def test_the_champions_picker_marks_nothing(self, reader, gang, settled):
        marks = {
            pickable.name: pickable.taken_for
            for group in offer_for(settled[EXCEPTED]).groups
            for pickable in group.options
        }

        assert marks == {name: "" for name in CHAMPION_ARCHETYPES}

    def test_taking_the_same_one_again_is_allowed_and_lands_on_him(
        self, reader, gang, settled, archetypes
    ):
        """Informing, never policing: the gang is Mutant and so may the
        champion be. Two picks, two holders, both alive."""
        choose(reader, gang, EXCEPTED, archetypes["Mutant"])

        held = Assignment.objects.filter(pickable=archetypes["Mutant"], archived=False)
        assert sorted(pick.gang is not None for pick in held) == [False, True]
        assert card_of(gang, EXCEPTED).questions[0].chosen == "Mutant"

    def test_neither_card_says_anything_about_the_repeat(
        self, reader, gang, settled, archetypes
    ):
        choose(reader, gang, EXCEPTED, archetypes["Mutant"])

        assert card_of(gang, EXCEPTED).remarks == []
        assert render_gang(gang).notes == []


class TestTheGangPageStaysFlat:
    """Two choices and a slot type that grows are rows for the page to
    read, never round trips for it to make."""

    def test_more_pickables_do_not_mean_more_queries(
        self, reader, gang, crew, archetypes, slot_type, django_assert_num_queries
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import add_picklist_member
        from n26.library.models import Picklist

        choose(reader, gang, "Outcast Leader", archetypes["Mutant"])
        page = reverse("n26-gang", args=[gang.pk])

        with CaptureQueriesContext(connection) as few:
            assert reader.get(page).status_code == 200

        offered = Picklist.objects.get(name="Outcast Archetypes")
        for index in range(20):
            add_picklist_member(
                offered, create_pickable(f"Archetype {index}", slot_type)
            )

        with django_assert_num_queries(len(few), exact=False):
            assert reader.get(page).status_code == 200
