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


@pytest.fixture
def budgets(default_pack):
    from n26.library.standard_content import STANDARD_CONTENT

    STANDARD_CONTENT["founding-budgets"].create()


@pytest.fixture
def venators(budgets):
    from n26.library.models import GangType

    return GangType.objects.get(name="Venators")


@pytest.fixture
def ranks(budgets):
    from n26.library.models import Subtype

    return {name: Subtype.objects.get(name=name) for name in ("Leader", "Champion")}


@pytest.fixture
def tester(db):
    return User.objects.create_user("player")


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
def hire(gang, tester, make_profile, make_statline):
    def make(name, *rank_rows):
        profile = make_profile(
            f"{name} entry", price=0, gang_type=gang.gang_type, pack=gang.gang_type.pack
        )
        make_statline(profile, movement=5, weapon_skill=4, toughness=3)
        with operation(gang, actor=tester) as op:
            model = op.hire(profile, name)
            for rank in rank_rows:
                op.assign(rank, miniature=model)
        return model

    return make


@pytest.fixture
def leader(hire, ranks):
    return hire("Rasp", ranks["Leader"])


@pytest.fixture
def ganger(hire):
    return hire("Vesh")


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
    allowance asks two questions however much it has spent.

    Pinned by what is asked rather than by a total: an equip page's total
    moves with the kit on the model, and what matters here is that the
    allowance costs a fixed pair of questions and that a model without
    one costs neither.
    """

    #: The gang reading which actions it has open. Matched on the head of
    #: the statement rather than on the table's name, because a fighter's
    #: own row carries a subquery over the same table saying what the
    #: gang's open visit brought.
    ACTIONS = 'SELECT "n26_action"."id"'
    #: What this model has spent under the founding action.
    SPEND = 'SUM("n26_ledgerevent"."trade_points_delta")'

    def asked(self, client, url):
        """Every query the page makes, measured after one warm request —
        the first request of a session writes its own row."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        assert client.get(url).status_code == 200
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        return [query["sql"] for query in captured.captured_queries]

    def reads_actions(self, asked):
        return [sql for sql in asked if sql.startswith(self.ACTIONS)]

    def reads_spend(self, asked):
        return [sql for sql in asked if self.SPEND in sql]

    def test_a_model_with_no_allowance_asks_neither_question(
        self, client, tester, ganger, legacy_list
    ):
        """Nothing raised the counter, so the page never finds out
        whether the gang is being founded at all."""
        client.force_login(tester)

        asked = self.asked(client, equip_url(ganger, legacy_list))

        assert self.reads_actions(asked) == []
        assert self.reads_spend(asked) == []

    def test_an_allowance_asks_each_question_once(
        self, client, tester, leader, legacy_list
    ):
        client.force_login(tester)

        asked = self.asked(client, equip_url(leader, legacy_list))

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

        assert len(self.reads_actions(asked)) == 1
        assert self.reads_spend(asked) == []
