"""A budgeted model's equip screen: what it counts, and what it says.

While the gang's Found and equip gang action is open and the model has an
allowance of its own, its equip screen is a different screen: every list
on it counts Trade Points, the purchases record the founding action
rather than any visit the gang has open, and the rail carries the tally
the decision is made against.

A model with no allowance, and any model once the action is complete,
gets exactly the screen it got before allowances existed — down to the
number of queries, which is the reason the allowance is settled off the
card the page has already built before anything is asked of the
database.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Action, Assignment, Gang
from n26.core.operations import operation
from n26.library.authoring import (
    create_collection,
    create_trading_post,
    create_wargear,
)

pytestmark = pytest.mark.django_db

FOUNDING = Action.Kind.FOUNDING

#: The colour <c-n26.founding-mark> paints itself. One component draws the
#: mark, so finding this on a page is finding the mark; change it there and
#: change it here.
MARK = "text-violet-600"

#: Trade Points summed off the log. Both readings a screen showing two pots
#: makes are this sum; what tells them apart is what they join to.
SPEND = 'SUM("n26_ledgerevent"."trade_points_delta")'

#: The gang's open Visit Trading Post spend: joined to the action and
#: narrowed to the one still open. The model's founding spend narrows on the
#: buyer instead and never mentions this, so counting these tells a page
#: asking the visit twice from a page asking it once.
VISIT_SPEND = '"n26_action"."closed_id" IS NULL'

#: The Venator entries these tests hire, as ``(entry, the subtype naming
#: its rank)``. A Hunter is a Specialist, which is how the gang list
#: marks the rank; the allied entry is ranked Champion and filed under a
#: heading of its own, so no founding figure names it.
GANG_LIST = [("Hunt Leader", "Leader"), ("Hunter", "Specialist")]
ALLIES = [("Bone Scrivener", "Champion")]


@pytest.fixture
def ranks(default_pack):
    from n26.library.models import Subtype

    return {
        name: Subtype.objects.create(name=name)
        for name in ("Leader", "Champion", "Specialist")
    }


@pytest.fixture
def library(ranks, make_profile, make_statline):
    """A Venator gang list and one allied entry, then the seed. Authored
    first, because the seed names the entries it finds."""
    from n26.library.authoring import add_built_in, create_category
    from n26.library.models import GangType
    from n26.library.standard_content import GANG_LIST_SECTION, STANDARD_CONTENT

    entries = {}

    def author(gang_type, section, name, rank):
        profile = make_profile(
            f"{gang_type.name} {name}",
            price=0,
            gang_type=gang_type,
            category=create_category(section, f"{gang_type.name} {rank} {section}"),
        )
        make_statline(profile, movement=5, weapon_skill=4, toughness=3)
        add_built_in(profile, ranks[rank])
        entries[name] = profile

    venators = GangType.objects.create(name="Venators")
    for name, rank in GANG_LIST:
        author(venators, GANG_LIST_SECTION, name, rank)
    allies = GangType.objects.create(name="Allies")
    for name, rank in ALLIES:
        author(allies, "Allies", name, rank)

    STANDARD_CONTENT["founding-budgets"].create()
    return entries


@pytest.fixture
def venators(library):
    from n26.library.models import GangType

    return GangType.objects.get(name="Venators")


@pytest.fixture
def tester(db):
    # Staff, because the founding budgets reach staff owners only while
    # they are being tested; the non-staff owner has a class of their own.
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def gang(venators, tester):
    """A gang founded the way the create screen founds one, so its Found
    and equip gang action is open."""
    gang = Gang.objects.create(
        name="The Long Hunt",
        owner=tester,
        gang_type=venators,
        starting_credits=1000,
        credits=1000,
    )
    with operation(gang, actor=tester) as op:
        op.found(venators)
    return gang


@pytest.fixture
def hire(gang, tester, library):
    def make(entry, name):
        with operation(gang, actor=tester) as op:
            return op.hire(library[entry], name)

    return make


@pytest.fixture
def leader(hire):
    return hire("Hunt Leader", "Rasp")


@pytest.fixture
def ganger(hire):
    """An ally the gang hired in: ranked Champion by its own book, and
    given no founding allowance by this one."""
    return hire("Bone Scrivener", "Vesh")


@pytest.fixture
def legacy_list(gang, tester):
    """The list a Gang Legacy grants: two items with Trade Point prices
    and one the post never stocks."""
    create_wargear("Mesh armour", price=15, trade_point_price=1)
    create_wargear("Flak plate", price=40, trade_point_price=3)
    create_wargear("Hunt banner", price=20, is_exclusive=True)
    from n26.library.models import Wargear

    collection = create_collection(
        "House Escher Equipment List",
        entries=list(Wargear.objects.all()),
    )
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)
    return collection


@pytest.fixture
def post(legacy_list):
    from n26.library.models import Wargear

    return create_trading_post("Trading Post", contains=[Wargear])


def equip_url(fighter, collection=None):
    url = reverse("n26-equip", args=[fighter.pk])
    return f"{url}?list={collection.pk}" if collection else url


def key_of(thing):
    return f"{thing._meta.label_lower}:{thing.pk}"


def wargear(name):
    from n26.library.models import Wargear

    return Wargear.objects.get(name=name)


def bought(gang, name):
    return Assignment.objects.get(gang_root=gang, wargear__name=name)


class TestWhatTheListCounts:
    """An equipment list counts Trade Points for a budgeted model and for
    nobody else, which is what the books mean by a combined figure."""

    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_a_budgeted_model_spends_them_on_a_list_line(
        self, client, gang, leader, legacy_list
    ):
        client.post(
            equip_url(leader, legacy_list), {"thing": key_of(wargear("Flak plate"))}
        )

        entry = bought(gang, "Flak plate").ledger_entry
        assert entry.trade_points == 3
        assert entry.action == gang.open_action(FOUNDING)

    def test_a_model_with_no_allowance_spends_none_on_the_same_line(
        self, client, gang, ganger, legacy_list
    ):
        client.post(
            equip_url(ganger, legacy_list), {"thing": key_of(wargear("Flak plate"))}
        )

        entry = bought(gang, "Flak plate").ledger_entry
        assert entry.trade_points == 0
        assert entry.action is None

    def test_nor_does_anybody_once_the_action_is_complete(
        self, client, gang, tester, leader, legacy_list
    ):
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))

        client.post(
            equip_url(leader, legacy_list), {"thing": key_of(wargear("Flak plate"))}
        )

        entry = bought(gang, "Flak plate").ledger_entry
        assert entry.trade_points == 0
        assert entry.action is None

    def test_an_exclusive_line_is_offered_and_counts_nothing(
        self, client, gang, leader, legacy_list
    ):
        """Being on the list is the whole of what Exclusive means, so the
        line stays — and it carries no Trade Point figure to count."""
        page = client.get(equip_url(leader, legacy_list)).content.decode()
        assert "Hunt banner" in page

        client.post(
            equip_url(leader, legacy_list), {"thing": key_of(wargear("Hunt banner"))}
        )

        assert bought(gang, "Hunt banner").ledger_entry.trade_points == 0

    def test_the_line_prints_the_figure_it_counts(
        self, client, leader, ganger, legacy_list
    ):
        """A hand-written list leaves the TP figure off, because nobody
        reading it is asking. A reader spending an allowance is."""
        budgeted = client.get(equip_url(leader, legacy_list))
        plain = client.get(equip_url(ganger, legacy_list))

        def figures(response):
            return [
                row.trade_points
                for row in response.context["catalogue"].all_rows()
                if row.name == "Flak plate"
            ]

        assert figures(budgeted) == [3]
        assert figures(plain) == [None]


class TestWhichActionAPurchaseCountsAgainst:
    """The model's own points go first. A visit the gang has open at the
    same time is a separate allowance and is left alone."""

    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_a_post_line_counts_against_the_founding_and_not_the_visit(
        self, client, gang, tester, leader, post
    ):
        with operation(gang, actor=tester) as op:
            op.visit_trading_post(brought=6)

        client.post(equip_url(leader, post), {"thing": key_of(wargear("Mesh armour"))})

        entry = bought(gang, "Mesh armour").ledger_entry
        assert entry.action == gang.open_action(FOUNDING)
        gang.refresh_from_db()
        assert gang.trade_points_left == 6

    def test_and_an_unbudgeted_model_still_counts_against_the_visit(
        self, client, gang, tester, ganger, post
    ):
        with operation(gang, actor=tester) as op:
            op.visit_trading_post(brought=6)

        client.post(equip_url(ganger, post), {"thing": key_of(wargear("Mesh armour"))})

        entry = bought(gang, "Mesh armour").ledger_entry
        assert entry.action == gang.open_visit
        gang.refresh_from_db()
        assert gang.trade_points_left == 5


class TestWhatTheScreenSays:
    """The tally the decision is made against, where the note about the
    post being shut would otherwise sit."""

    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    def test_the_tally_is_on_the_page(self, client, leader, legacy_list):
        response = client.get(equip_url(leader, legacy_list))
        body = response.content.decode()

        assert response.context["founding_budget"].granted == 5
        assert "Founding Trade Points" in body
        for label in ("Available", "Spent", "Remaining"):
            assert label in body

    def test_it_moves_as_the_model_spends(self, client, leader, legacy_list):
        client.post(
            equip_url(leader, legacy_list), {"thing": key_of(wargear("Flak plate"))}
        )

        budget = client.get(equip_url(leader, legacy_list)).context["founding_budget"]
        assert (budget.granted, budget.spent, budget.remaining) == (5, 3, 2)

    def test_the_post_being_shut_is_not_mentioned(self, client, leader, post):
        """A model with an allowance has somewhere for its Trade Points to
        go, so there is nothing to tell it about the post."""
        response = client.get(equip_url(leader, post))

        assert response.context["post_is_shut"] is False
        assert "Not tracking TP" not in response.content.decode()

    def test_a_model_with_no_allowance_is_told_the_post_is_shut(
        self, client, ganger, post
    ):
        response = client.get(equip_url(ganger, post))

        assert response.context["post_is_shut"] is True
        assert "Not tracking TP" in response.content.decode()

    def test_nothing_is_drawn_once_the_action_is_complete(
        self, client, gang, tester, leader, legacy_list
    ):
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))

        response = client.get(equip_url(leader, legacy_list))

        assert response.context["founding_budget"] is None
        assert "Founding Trade Points" not in response.content.decode()

    def test_the_tally_carries_the_founding_mark(self, client, leader, legacy_list):
        """The same mark the action carries on the gang page and the model
        cards carry beside their figures, so one feature is read once."""
        body = client.get(equip_url(leader, legacy_list)).content.decode()

        heading = body.index("Founding Trade Points")
        assert MARK in body[body.rindex("<p class=", 0, heading) : heading]


class TestBothPotsAtOnce:
    """A model with an allowance whose gang also has a visit open. The two
    are separate allowances, and the rail says which one this page spends
    rather than leaving two Trade Point figures to be read the wrong way
    round."""

    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    @pytest.fixture
    def visiting(self, gang, tester):
        with operation(gang, actor=tester) as op:
            op.visit_trading_post(brought=6)
        gang.refresh_from_db()
        return gang

    def test_both_blocks_are_drawn(self, client, leader, post, visiting):
        response = client.get(equip_url(leader, post))
        body = response.content.decode()

        assert response.context["visit_beside_founding"] is True
        assert response.context["visit_trade_points_left"] == 6
        assert "Founding Trade Points" in body
        assert "Trading Post visit" in body
        assert "6 TP" in body
        assert "Manage visit" in body

    def test_the_visit_block_says_which_pot_this_page_spends(
        self, client, leader, post, visiting
    ):
        said = " ".join(client.get(equip_url(leader, post)).content.decode().split())

        assert "founding Trade Points, not against the visit" in said

    def test_the_allowance_alone_draws_no_visit_block(
        self, client, leader, legacy_list
    ):
        """No visit open, so there is no second pot to tell apart."""
        response = client.get(equip_url(leader, legacy_list))

        assert response.context["visit_beside_founding"] is False
        assert "Trading Post visit" not in response.content.decode()

    def test_the_post_being_shut_is_still_the_one_note_it_silences(
        self, client, leader, post
    ):
        """An allowance and no visit: the model has somewhere for its Trade
        Points to go, so nothing is said about the post."""
        body = client.get(equip_url(leader, post)).content.decode()

        assert "Not tracking TP" not in body
        assert "Trading Post visit" not in body

    def test_the_block_costs_one_reading_of_the_visit_and_no_more(
        self, client, leader, post, visiting
    ):
        """Two readings of what the visit has spent: the figure strip's,
        and the one the view works out for this block. The gang
        deliberately never caches that sum, so each ask is a query — a
        third would mean the block had gone and asked for itself instead
        of drawing what the view handed it.

        Counted by what is asked rather than by a page total, so an
        unrelated change to the equip screen fails elsewhere and this
        keeps saying what it is about.
        """
        asked = queries_for(client, equip_url(leader, post))

        visit_reads = [sql for sql in asked if SPEND in sql and VISIT_SPEND in sql]
        assert len(visit_reads) == 2

    def test_the_model_spend_is_still_asked_once(self, client, leader, post, visiting):
        """The allowance's own sum narrows on the buyer and never joins the
        open visit, so the second pot has not quietly doubled it."""
        asked = queries_for(client, equip_url(leader, post))

        own = [sql for sql in asked if SPEND in sql and VISIT_SPEND not in sql]
        assert len(own) == 1


class TestAnOwnerTheBudgetsDoNotReachYet:
    """While the founding budgets are being tested they reach staff owners
    only, the same readers as the Actions square that completes the
    founding. Every other owner's screens are read exactly as they were
    before budgets existed: no tally, list lines counting nothing, the
    post-is-shut note in its old place, and a purchase naming no action."""

    @pytest.fixture(autouse=True)
    def signed_in_as_a_plain_owner(self, client, gang):
        plain = User.objects.create_user("plain-owner")
        gang.owner = plain
        gang.save(update_fields=["owner"])
        client.force_login(plain)

    def test_the_tally_is_not_drawn(self, client, leader, legacy_list):
        response = client.get(equip_url(leader, legacy_list))

        assert response.context["founding_budget"] is None
        assert "Founding Trade Points" not in response.content.decode()

    def test_the_post_is_still_said_to_be_shut(self, client, leader, post):
        response = client.get(equip_url(leader, post))

        assert response.context["post_is_shut"] is True
        assert "Not tracking TP" in response.content.decode()

    def test_a_list_purchase_counts_nothing_and_names_no_action(
        self, client, gang, leader, legacy_list
    ):
        client.post(
            equip_url(leader, legacy_list), {"thing": key_of(wargear("Flak plate"))}
        )

        entry = bought(gang, "Flak plate").ledger_entry
        assert entry.trade_points == 0
        assert entry.action is None
        assert entry.spent_by is None


def queries_for(client, url):
    """Every query a page makes, measured after one warm request — the
    first request of a session writes its own row."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    assert client.get(url).status_code == 200
    with CaptureQueriesContext(connection) as captured:
        assert client.get(url).status_code == 200
    return [query["sql"] for query in captured.captured_queries]


def visit_control(body):
    """The markup of the control that offers a Trading Post visit."""
    label = body.index("Set up Trading Post visit")
    return body[body.rindex("<", 0, body.rindex("<", 0, label)) : label]


class TestTheWayIntoAVisitFromTheRail:
    """The Not tracking TP block offers to start a visit. While the gang is
    part-way through founding there is nowhere for that offer to go — a
    gang holds one action of each kind — so the button is drawn dead with
    the reason beside it rather than leading to a page that refuses."""

    def test_the_old_wording_is_gone(self, client, tester, ganger, post):
        client.force_login(tester)

        assert (
            "Set up TP visit"
            not in client.get(equip_url(ganger, post)).content.decode()
        )

    def test_a_staff_owner_gets_the_button_dead_and_the_reason(
        self, client, tester, ganger, post
    ):
        client.force_login(tester)

        response = client.get(equip_url(ganger, post))
        body = response.content.decode()

        assert response.context["founding_blocks_visit"] is True
        assert "Not tracking TP" in body
        assert "disabled" in visit_control(body)
        assert "You can have only one of these actions open at a time." in body

    def test_the_dead_button_lets_the_pointer_reach_its_tooltip(
        self, client, tester, ganger, post
    ):
        """A disabled control emits no mouse events, so left bare it would
        be the pointer's target and the tooltip around it would never
        open. The button is drawn inert inside a span, and the span is
        what the pointer hits. The tooltip's own words are in the page
        either way, so nothing else here can catch this."""
        client.force_login(tester)

        control = visit_control(client.get(equip_url(ganger, post)).content.decode())

        assert "pointer-events-none" in control
        assert control.lstrip().startswith("<span")
        assert "cursor-not-allowed" in control
        # The reason again, off screen: a tooltip that only opens
        # under a pointer leaves everybody else a dead button.
        assert 'aria-describedby="n26-visit-shut-rail"' in control

    def test_an_owner_the_founding_does_not_reach_keeps_the_way_in(
        self, client, gang, ganger, post
    ):
        """Every gang carries an open founding action, and an owner the
        feature has not reached is given no way to close one. Shutting the
        button for them would take visits away with nothing in their
        place."""
        plain = User.objects.create_user("plain-owner")
        gang.owner = plain
        gang.save(update_fields=["owner"])
        client.force_login(plain)

        response = client.get(equip_url(ganger, post))
        body = response.content.decode()

        assert response.context["founding_blocks_visit"] is False
        assert "disabled" not in visit_control(body)
        assert reverse("n26-gang-trade-points", args=[gang.pk]) in visit_control(body)
        assert "You can have only one of these actions open at a time." not in body

    def test_completing_the_founding_opens_the_way(
        self, client, gang, tester, ganger, post
    ):
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))
        client.force_login(tester)

        response = client.get(equip_url(ganger, post))

        assert response.context["founding_blocks_visit"] is False
        assert "disabled" not in visit_control(response.content.decode())

    def test_a_screen_that_never_mentions_the_post_asks_nothing(
        self, client, tester, ganger, legacy_list
    ):
        """The question costs the gang's open actions, so it is asked only
        where the block that offers a visit is drawn."""
        client.force_login(tester)

        response = client.get(equip_url(ganger, legacy_list))

        assert response.context["post_is_shut"] is False
        assert response.context["founding_blocks_visit"] is False


class TestGoingPastIt:
    """The overspend question, asked with the model's own figures."""

    @pytest.fixture(autouse=True)
    def signed_in(self, client, tester):
        client.force_login(tester)

    @pytest.fixture
    def spent_four(self, client, leader, legacy_list):
        """Four of the five gone: a plate and a mesh."""
        for name in ("Flak plate", "Mesh armour"):
            client.post(
                equip_url(leader, legacy_list), {"thing": key_of(wargear(name))}
            )

    def test_the_click_is_answered_with_a_question(
        self, client, gang, leader, legacy_list, spent_four
    ):
        response = client.post(
            equip_url(leader, legacy_list), {"thing": key_of(wargear("Flak plate"))}
        )
        body = response.content.decode()

        assert response.status_code == 200
        assert "Not enough Trade Points" in body
        assert "Buy Flak plate anyway" in body
        # The model's own name, because the allowance is the model's.
        assert "Rasp has 1" in body
        assert (
            Assignment.objects.filter(
                gang_root=gang, wargear__name="Flak plate"
            ).count()
            == 1
        )

    def test_the_arithmetic_is_the_models_own(
        self, client, leader, legacy_list, spent_four
    ):
        body = client.post(
            equip_url(leader, legacy_list), {"thing": key_of(wargear("Flak plate"))}
        ).content.decode()

        for label in (
            "Available",
            "Spent",
            "Remaining",
            "This purchase",
            "Remaining after",
        ):
            assert label in body
        assert "-2" in body

    def test_confirming_buys_it_against_the_founding_action(
        self, client, gang, leader, legacy_list, spent_four
    ):
        response = client.post(
            equip_url(leader, legacy_list),
            {"thing": key_of(wargear("Flak plate")), "confirmed": "1"},
        )

        assert response.status_code == 302
        entries = [
            row.ledger_entry
            for row in Assignment.objects.filter(
                gang_root=gang, wargear__name="Flak plate"
            )
        ]
        assert len(entries) == 2
        assert {entry.action for entry in entries} == {gang.open_action(FOUNDING)}


class TestTheQueryBudget:
    """A model with no allowance asks nothing extra, and one with an
    allowance asks three questions however much it has spent.

    Pinned by what is asked rather than by a total: an equip page's total
    moves with the kit on the model, and what matters here is that the
    allowance costs a fixed set of questions and that a model without one
    asks none of them.
    """

    #: The gang reading which actions it has open. Matched on the head of
    #: the statement rather than on the table's name, because a fighter's
    #: own row carries a subquery over the same table saying what the
    #: gang's open visit brought.
    ACTIONS = 'SELECT "n26_action"."id"'
    #: The standard counter, so a homebrew one of the same name is not
    #: mistaken for it. Named by its pack's slug, which is the join that
    #: tells it from the counters a card's modifiers bring along.
    COUNTER = '"library_contentpack"'

    def asked(self, client, url):
        return queries_for(client, url)

    def reads_actions(self, asked):
        return [sql for sql in asked if sql.startswith(self.ACTIONS)]

    def reads_counter(self, asked):
        return [
            sql for sql in asked if '"library_counter"' in sql and self.COUNTER in sql
        ]

    def reads_spend(self, asked):
        return [sql for sql in asked if SPEND in sql]

    def test_a_model_with_no_allowance_asks_none_of_them(
        self, client, tester, ganger, legacy_list
    ):
        """Nothing on the card named the counter, so the page never asks
        the library about it and never finds out whether the gang is
        being founded at all."""
        client.force_login(tester)

        asked = self.asked(client, equip_url(ganger, legacy_list))

        assert self.reads_counter(asked) == []
        assert self.reads_actions(asked) == []
        assert self.reads_spend(asked) == []

    def test_an_allowance_asks_each_question_once(
        self, client, tester, leader, legacy_list
    ):
        client.force_login(tester)

        asked = self.asked(client, equip_url(leader, legacy_list))

        assert len(self.reads_counter(asked)) == 1
        assert len(self.reads_actions(asked)) == 1
        assert len(self.reads_spend(asked)) == 1

    def test_and_asks_no_more_however_much_has_been_spent(
        self, client, tester, leader, legacy_list
    ):
        client.force_login(tester)
        url = equip_url(leader, legacy_list)
        for name in ("Flak plate", "Mesh armour"):
            client.post(url, {"thing": key_of(wargear(name))})

        asked = self.asked(client, url)

        assert len(self.reads_counter(asked)) == 1
        assert len(self.reads_actions(asked)) == 1
        assert len(self.reads_spend(asked)) == 1

    def test_a_completed_action_asks_nothing_about_spending(
        self, client, tester, gang, leader, legacy_list
    ):
        """The reading still stands, so the gang is asked which actions
        it has open — and with none open there is nothing to have spent
        against."""
        with operation(gang, actor=tester) as op:
            op.close_action(gang.open_action(FOUNDING))
        client.force_login(tester)

        asked = self.asked(client, equip_url(leader, legacy_list))

        assert len(self.reads_counter(asked)) == 1
        assert len(self.reads_actions(asked)) == 1
        assert self.reads_spend(asked) == []
