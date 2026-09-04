"""Trade Points: minted for a trip, spent at the post, lost at the end.

The rules give a gang Trade Points when its Leaders and Champions visit a
trading post — 2 a Leader, 1 a Champion — and take back whatever is left
when the visit ends. Credits are nothing like that: they are the gang's,
they persist, and spending past them is the one thing this edition
refuses.

So Trade Points are kept the other way round, per design/collections.md:
an action the gang opens and closes, carrying what the visit brought,
and a sum over the ledger rather than a second pinned figure. What makes
a trip a trip is that action — a purchase records the one it counted
against, so what a visit has spent is what points back at it.

Four claims, and each has a test below:

* a list an author wrote out charges credits; a post swept together *by*
  Trade Point prices charges points as well;
* what is left is what the visit brought less the points the purchases
  counting against it record, and a refund on the same trip hands its
  points back;
* a second visit starts from nothing spent, even at the same figure, and
  cannot open over one still open;
* overspending is allowed and never refused — only credits refuse.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import EQUIPMENT_LIST, TRADING_POST, browse, terms_for
from n26.core.models import LedgerEvent
from n26.core.reconcile import assert_reconciled
from n26.core.trading import receipt_for, visitors
from n26.tests.sandbox.actions import (
    add_entry,
    assign,
    buy,
    create_category,
    create_collection,
    create_subtype,
    create_trading_post,
    create_wargear,
    found_gang,
    hire_with_option,
    leave_trading_post,
    refund,
    visit_trading_post,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def fighter(gang, make_profile):
    return hire_with_option(gang, make_profile("Escher Ganger", price=55), "Yolanda")


@pytest.fixture
def kit(db):
    """Two pieces of wargear, both priced in credits and in Trade Points."""
    create_category("Armour", "Armour", position=0)
    return {
        "mesh": create_wargear("Mesh armour", price=15, trade_point_price=1),
        "plate": create_wargear("Flak plate", price=40, trade_point_price=3),
    }


@pytest.fixture
def post(kit):
    return create_trading_post("Trading Post", contains=[type(kit["mesh"])])


@pytest.fixture
def equipment_list(kit):
    """A curated list holding the same two items at the same prices."""
    listed = create_collection("Escher Equipment List")
    for thing in kit.values():
        add_entry(listed, thing)
    return listed


def line_for(view, name):
    return next(line for line in view.all_lines() if line.name == name)


class TestWhichSurfacesCharge:
    """Charging is the buying flow's decision, and the flow reads it off
    the collection's definition: membership by Trade Point price is what
    makes somewhere a trading post."""

    def test_a_post_swept_together_by_trade_point_prices_charges_them(self, post):
        assert terms_for(post) == TRADING_POST

    def test_a_list_an_author_wrote_out_by_hand_does_not(self, equipment_list):
        assert terms_for(equipment_list) == EQUIPMENT_LIST

    def test_a_browse_told_no_terms_uses_the_collections_own(self, post):
        """What the buying screens do: they name the list and let the
        definition settle how it charges."""
        assert all(line.charges_trade_points for line in browse(post).all_lines())

    def test_and_a_list_browsed_the_same_way_charges_nothing(self, equipment_list):
        assert not any(
            line.charges_trade_points for line in browse(equipment_list).all_lines()
        )

    def test_a_list_shows_the_figures_it_never_charges(self, gang, fighter, kit):
        """An equipment list prints what the book prints. Buying from it
        moves credits and no Trade Points at all."""
        listed = create_collection("Escher Equipment List")
        add_entry(listed, kit["mesh"])
        view = browse(listed, EQUIPMENT_LIST)

        bought = buy(fighter, line_for(view, "Mesh armour"))

        assert bought.ledger_entry.paid == 15
        assert bought.ledger_entry.trade_points == 0

    def test_the_same_collection_charges_when_browsed_as_a_trip(
        self, gang, fighter, post
    ):
        view = browse(post, TRADING_POST)

        bought = buy(fighter, line_for(view, "Mesh armour"))

        assert bought.ledger_entry.paid == 15
        assert bought.ledger_entry.trade_points == 1


class TestWhatIsLeft:
    def test_a_gang_that_has_never_been_to_a_post_has_no_visit_open(self, gang):
        """Not an allowance of nothing: the rules shut the post to a gang
        where nobody performed the action, so there is no figure at all."""
        assert gang.starting_trade_points is None
        assert gang.visiting_trading_post is False
        assert gang.trade_points_left is None

    def test_an_allowance_is_what_there_is_to_spend(self, gang):
        visit_trading_post(gang, brought=4)

        gang.refresh_from_db()
        assert gang.trade_points_left == 4

    def test_spending_at_the_post_counts_down(self, gang, fighter, post):
        visit_trading_post(gang, brought=4)
        view = browse(post, TRADING_POST)

        buy(fighter, line_for(view, "Mesh armour"))

        gang.refresh_from_db()
        assert gang.trade_points_spent == 1
        assert gang.trade_points_left == 3

    def test_buying_from_a_list_does_not(self, gang, fighter, equipment_list):
        """The allowance is untouched by a purchase that never charged it,
        even where the item has a Trade Point price of its own."""
        visit_trading_post(gang, brought=4)
        view = browse(equipment_list, EQUIPMENT_LIST)

        buy(fighter, line_for(view, "Mesh armour"))

        gang.refresh_from_db()
        assert gang.trade_points_left == 4

    def test_a_refund_on_the_same_trip_hands_the_points_back(self, gang, fighter, post):
        """Credits and Trade Points come back together, because a refund
        undoes the purchase whole."""
        visit_trading_post(gang, brought=4)
        view = browse(post, TRADING_POST)
        bought = buy(fighter, line_for(view, "Mesh armour"))

        refund(bought)

        gang.refresh_from_db()
        assert gang.trade_points_left == 4
        assert_reconciled(gang)


class TestEndingTheAction:
    def test_finishing_the_action_shuts_the_post(self, gang, fighter, post):
        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))

        leave_trading_post(gang)

        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        assert gang.trade_points_left is None

    def test_a_second_visit_cannot_open_over_an_open_one(self, gang):
        """A gang performs one at a time, and the act itself says so:
        purchases made while two were open could not say which of them
        they counted against."""
        from n26.core.operations import Refusal

        visit_trading_post(gang, brought=4)

        with pytest.raises(Refusal):
            visit_trading_post(gang, brought=4)

    def test_what_went_before_stops_counting(self, gang, fighter, post):
        """A second trip is measured from its own allowance. The first
        trip's spending is history, not a debt carried forward."""
        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))

        leave_trading_post(gang)
        visit_trading_post(gang, brought=4)

        gang.refresh_from_db()
        assert gang.trade_points_spent == 0
        assert gang.trade_points_left == 4

    def test_handing_back_an_earlier_trips_kit_does_not_fund_this_one(
        self, gang, fighter, post
    ):
        """A refund belongs to the trip its purchase belonged to.

        The refund event is written whenever the owner gets round to it,
        which may be trips later. Measured by event time, the undoing of
        a purchase this trip never counted would land inside it — and
        handing back old kit would mint Trade Points the visit never
        brought.
        """
        visit_trading_post(gang, brought=4)
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))

        leave_trading_post(gang)
        visit_trading_post(gang, brought=4)
        refund(bought)

        gang.refresh_from_db()
        assert gang.trade_points_spent == 0
        assert gang.trade_points_left == 4

    def test_a_refund_on_the_same_trip_puts_the_points_back(self, gang, fighter, post):
        """The other side of the same rule: within one trip the purchase
        and its undoing both count, so the allowance comes back whole."""
        visit_trading_post(gang, brought=4)
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))
        spent = gang.trade_points_spent
        assert spent > 0, (
            "the fixture must charge Trade Points for this to mean anything"
        )

        refund(bought)

        gang.refresh_from_db()
        assert gang.trade_points_spent == 0
        assert gang.trade_points_left == 4

    def test_a_second_trip_at_the_same_figure_starts_from_nothing_spent(
        self, gang, fighter, post
    ):
        """Two trips at the same figure are two trips. Each is its own
        action, so the first one's spending never counts against the
        second — a guard that treated an unchanged figure as nothing to
        do would leave it counting."""
        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))
        gang.refresh_from_db()
        assert gang.trade_points_left == 3

        leave_trading_post(gang)
        visit_trading_post(gang, brought=4)

        gang.refresh_from_db()
        assert gang.trade_points_left == 4
        # Opened, closed, opened again: the boundary is written every
        # time, whatever the figure.
        assert (
            LedgerEvent.objects.filter(
                gang=gang, kind=LedgerEvent.Kind.TRADE_POINTS_SET
            ).count()
            == 3
        )

    def test_the_visit_moves_no_money(self, gang):
        """It is minted, not bought. Credits, rating and the books are
        exactly where they were."""
        before = gang.credits

        visit_trading_post(gang, brought=4)

        gang.refresh_from_db()
        assert gang.credits == before
        assert gang.rating == 0
        assert_reconciled(gang)


class TestOverspending:
    """Credits are the single enforced resource. Trade Points inform: a
    surface asks whether an overspend was meant, and the operation itself
    never refuses one."""

    def test_spending_past_the_allowance_goes_through(self, gang, fighter, post):
        visit_trading_post(gang, brought=1)
        view = browse(post, TRADING_POST)

        bought = buy(fighter, line_for(view, "Flak plate"))

        assert bought.ledger_entry.trade_points == 3
        gang.refresh_from_db()
        assert gang.trade_points_left == -2

    def test_buying_with_the_post_shut_goes_through_too(self, gang, fighter, post):
        """The rules only open the post to a gang whose fighter performed
        the action. Nothing here enforces that — the purchase asks first
        and then records what it spent, and the gang still has no visit
        for the points to count against."""
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))

        assert bought.ledger_entry.trade_points == 1
        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        assert gang.trade_points_left is None
        assert_reconciled(gang)


def only(gang, *names):
    """The roster as a cast list, with just these fighters going."""
    chosen = {
        str(one.miniature.pk) for one in visitors(gang) if one.miniature.name in names
    }
    return visitors(gang, chosen)


class TestWhoPerformsTheAction:
    """Any fighter may go, and the two named ranks bring points with them.
    Who went is recorded per model, because the rules give each model one
    Post-cycle Action and a figure cannot say whose it was."""

    @pytest.fixture
    def ranked(self, gang, make_profile, make_statline):
        """A Leader, a Champion and a Ganger, each holding their rank."""
        made = {}
        for name, rank in [("Rasp", "Leader"), ("Kel", "Champion"), ("Tuk", None)]:
            profile = make_profile(f"{name} entry", price=50)
            make_statline(profile)
            model = hire_with_option(gang, profile, name)
            if rank:
                assign(create_subtype(rank), miniature=model)
            made[name] = model
        return made

    def test_only_the_paying_ranks_are_offered(self, gang, ranked):
        """A fighter who brings nothing is a choice with no consequence.
        Equipping is the other half and has no such limit."""
        offered = {one.miniature.name: one for one in visitors(gang)}

        assert set(offered) == {"Rasp", "Kel"}
        assert offered["Rasp"].trade_points == 2
        assert offered["Kel"].trade_points == 1
        assert offered["Rasp"].visiting is True
        assert offered["Kel"].visiting is True

    def test_a_fighter_who_brings_nothing_is_not_among_them(self, gang, ranked):
        assert "Tuk" not in {one.miniature.name for one in visitors(gang)}

    def test_the_receipt_names_who_went_and_what_they_brought(self, gang, ranked):
        visit_trading_post(gang, visitors(gang))

        gang.refresh_from_db()
        receipt = receipt_for(gang)
        assert receipt.available == 3
        assert receipt.spent == 0
        assert receipt.remaining == 3
        assert {one.name for one in receipt.contributors} == {"Rasp", "Kel"}
        assert receipt.summary == "Leader, Champion"

    def test_the_summary_counts_repeated_ranks(self, gang, ranked, make_profile):
        from n26.library.models import Subtype

        profile = make_profile("Vesh entry", price=50)
        model = hire_with_option(gang, profile, "Vesh")
        # The rank already exists — the fixture authored it. Authoring it
        # again trips the per-pack unique name.
        assign(Subtype.objects.get(name="Champion"), miniature=model)

        visit_trading_post(gang, visitors(gang))

        gang.refresh_from_db()
        assert receipt_for(gang).summary == "Leader, Champion × 2"

    def test_each_visit_is_recorded_against_the_model(self, gang, ranked):
        visit_trading_post(gang, visitors(gang))

        went = LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.VISITED_TRADING_POST
        )
        assert {event.miniature.name for event in went} == {"Rasp", "Kel"}
        assert {event.note for event in went} == {"Leader", "Champion"}
        # The points are the gang's, counted once on the opening event.
        assert all(event.trade_points_delta == 0 for event in went)

    def test_a_second_visit_reads_its_own_cast(self, gang, ranked):
        visit_trading_post(gang, visitors(gang))

        leave_trading_post(gang)
        visit_trading_post(gang, only(gang, "Rasp"))

        gang.refresh_from_db()
        receipt = receipt_for(gang)
        assert receipt.available == 2
        assert {one.name for one in receipt.contributors} == {"Rasp"}

    def test_the_post_being_shut_has_no_receipt(self, gang, ranked):
        assert receipt_for(gang) is None

    def test_the_receipt_counts_down_as_the_visit_spends(self, gang, ranked, post):
        visit_trading_post(gang, visitors(gang))
        buy(
            ranked["Rasp"],
            line_for(browse(post, TRADING_POST), "Flak plate"),
        )

        gang.refresh_from_db()
        receipt = receipt_for(gang)
        assert (receipt.available, receipt.spent, receipt.remaining) == (3, 3, 0)


class TestWhatTheHistorySays:
    """The ledger records Trade Points on the purchase that spent them, so
    the gang's history can say what a trip cost as well as what it bought."""

    def test_a_purchase_reports_the_points_it_spent(self, gang, fighter, post):
        from n26.core import history

        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))

        bought = [act for act in history.build(gang) if "bought" in act.spans[0].text][
            -1
        ]
        assert bought.trade_points == -3
        assert bought.credits == -40

    def test_a_purchase_that_spent_none_reports_none(self, gang, fighter, kit):
        from n26.core import history

        listed = create_collection("Escher Equipment List")
        add_entry(listed, kit["plate"])
        buy(fighter, line_for(browse(listed, EQUIPMENT_LIST), "Flak plate"))

        bought = [act for act in history.build(gang) if "bought" in act.spans[0].text][
            -1
        ]
        assert bought.trade_points == 0

    def test_a_refund_hands_them_back_in_the_telling(self, gang, fighter, post):
        from n26.core import history

        visit_trading_post(gang, brought=4)
        line = line_for(browse(post, TRADING_POST), "Flak plate")
        refund(buy(fighter, line))

        returned = [
            act for act in history.build(gang) if "refund" in act.spans[-1].text
        ][-1]
        assert returned.trade_points == 3

    def test_the_notes_that_carry_the_figures_stay_off_the_page(self, gang):
        """The note on these records is a carrier — the figure a visit
        brought, the word that says one closed, the rank a fighter went
        as. Each is already in the sentence, and printed under it would
        put bookkeeping on the page."""
        from n26.core import history

        visit_trading_post(gang, brought=4)
        leave_trading_post(gang)

        told = history.build(gang)[-2:]
        assert [act.note for act in told] == ["", ""]
        assert "closed" not in " ".join(span.text for act in told for span in act.spans)

    def test_opening_a_visit_spends_nothing(self, gang):
        """The points a visit brings are not a transaction — they arrive,
        and the line that says so moves no figure."""
        from n26.core import history

        visit_trading_post(gang, brought=4)

        opened = history.build(gang)[-1]
        assert opened.trade_points == 0
        assert opened.credits == 0


class TestWhatAPurchaseCountsAgainst:
    """A purchase records the action it counted against, so what a visit
    has spent is what points back at it rather than what happens to fall
    inside a stretch of time."""

    def test_a_purchase_at_the_post_records_the_open_visit(self, gang, fighter, post):
        visit_trading_post(gang, brought=4)

        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))

        gang.refresh_from_db()
        assert bought.ledger_entry.action == gang.open_visit

    def test_a_purchase_from_a_list_records_nothing(
        self, gang, fighter, equipment_list
    ):
        """Buying from an equipment list is not part of the visit, even
        with one open: recording it against the visit would make the
        visit's own figures a lie."""
        visit_trading_post(gang, brought=4)

        bought = buy(
            fighter, line_for(browse(equipment_list, EQUIPMENT_LIST), "Mesh armour")
        )

        assert bought.ledger_entry.action is None

    def test_a_purchase_with_the_post_shut_records_nothing(self, gang, fighter, post):
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))

        assert bought.ledger_entry.action is None

    def test_what_an_action_spent_is_what_the_visit_spent(self, gang, fighter, post):
        """The two arithmetics agree while a visit is open: everything it
        has spent points at it."""
        from n26.core.reconcile import trade_points_spent_for

        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))

        gang.refresh_from_db()
        assert trade_points_spent_for(gang.open_visit) == 3
        assert gang.trade_points_spent == 3

    def test_a_refund_returns_the_points_to_the_action_that_paid(
        self, gang, fighter, post
    ):
        """The refund's event sits on the assignment the purchase made, so
        it lands on the same action however long afterwards it happens."""
        from n26.core.reconcile import trade_points_spent_for

        visit_trading_post(gang, brought=4)
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))
        gang.refresh_from_db()
        visit = gang.open_visit

        refund(bought)

        assert trade_points_spent_for(visit) == 0
        gang.refresh_from_db()
        assert gang.trade_points_left == 4
        assert_reconciled(gang)

    def test_a_purchase_naming_no_action_is_counted_all_the_same(
        self, gang, fighter, post
    ):
        """A purchase written before the visit had a row to point at names
        no action, and the visit it belongs to is found instead by when
        its assignment was created, measured from the boundary the visit
        wrote. The figure comes out the same either way."""
        from n26.core.models import LedgerEntry

        visit_trading_post(gang, brought=4)
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))
        gang.refresh_from_db()
        stamped = gang.trade_points_spent

        LedgerEntry.objects.filter(pk=bought.ledger_entry.pk).update(action=None)

        gang.refresh_from_db()
        assert stamped == 3
        assert gang.trade_points_spent == stamped
        assert gang.trade_points_left == 1

    def test_a_closed_action_still_says_what_it_spent(self, gang, fighter, post):
        """The figure survives the visit ending. What an action spent is
        what points at it, so a visit two trips back can still be asked
        and still answers with its own arithmetic."""
        from n26.core.reconcile import trade_points_spent_for

        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))
        gang.refresh_from_db()
        visit = gang.open_visit

        leave_trading_post(gang)
        visit_trading_post(gang, brought=4)

        assert trade_points_spent_for(visit) == 3

    def test_a_later_refund_never_funds_the_visit_that_is_open(
        self, gang, fighter, post
    ):
        """Handing back kit bought on an earlier visit gives its points to
        that visit, which is closed. The open one is untouched."""
        from n26.core.reconcile import trade_points_spent_for

        visit_trading_post(gang, brought=4)
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))
        gang.refresh_from_db()
        earlier = gang.open_visit
        leave_trading_post(gang)
        visit_trading_post(gang, brought=4)

        refund(bought)

        gang.refresh_from_db()
        assert trade_points_spent_for(earlier) == 0
        assert trade_points_spent_for(gang.open_visit) == 0
        assert gang.trade_points_left == 4


class TestTheActionIsTheState:
    """What a screen reads is the action row. The figure kept beside it on
    the gang is a copy, and where the two disagree the row wins."""

    def test_the_receipt_reads_the_action(self, gang):
        from n26.core.models import Gang

        visit_trading_post(gang, brought=4)
        Gang.objects.filter(pk=gang.pk).update(starting_trade_points=99)

        gang.refresh_from_db()
        assert receipt_for(gang).available == 4

    def test_what_is_left_reads_the_action(self, gang):
        from n26.core.models import Gang

        visit_trading_post(gang, brought=4)
        Gang.objects.filter(pk=gang.pk).update(starting_trade_points=99)

        gang.refresh_from_db()
        assert gang.trade_points_left == 4

    def test_the_post_is_shut_where_no_action_is_open(self, gang):
        """A figure with no action behind it is not a visit."""
        from n26.core.models import Gang

        Gang.objects.filter(pk=gang.pk).update(starting_trade_points=4)

        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        assert receipt_for(gang) is None


class TestOpeningTheVisitsThatWereAlreadyOpen:
    """The data migration behind the change: a gang at a post before there
    were action rows gets one, pointing at the boundary event its visit
    already wrote, and the purchases the figure was read from are stamped
    with it. Run here against the live models, which is what the migration
    sees on the way past."""

    def run_it(self):
        import importlib

        from django.apps import apps

        module = importlib.import_module(
            "n26.core.migrations.0044_the_open_visit_becomes_an_action"
        )
        module.open_the_visits(apps, None)

    def undo(self, gang):
        """Put the gang back as it was before actions were rows: the
        figure and the boundary event, and nothing else."""
        from n26.core.models import Action

        Action.objects.filter(gang=gang).delete()
        gang.refresh_from_db()
        assert gang.starting_trade_points is not None
        assert gang.visiting_trading_post is False

    @pytest.fixture
    def mid_visit(self, gang, fighter, post, equipment_list):
        """A gang partway through a visit, with one purchase that counted
        Trade Points and one that did not."""
        visit_trading_post(gang, brought=4)
        counted = buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))
        free = buy(
            fighter, line_for(browse(equipment_list, EQUIPMENT_LIST), "Mesh armour")
        )
        gang.refresh_from_db()
        assert gang.trade_points_left == 1
        self.undo(gang)
        return {"counted": counted, "free": free}

    def test_it_opens_an_action_for_the_visit(self, gang, mid_visit):
        self.run_it()

        gang.refresh_from_db()
        assert gang.visiting_trading_post is True
        assert gang.open_visit.trade_points == 4

    def test_it_points_the_action_at_the_boundary_the_visit_wrote(
        self, gang, mid_visit
    ):
        """Which is what lets the receipt still name who performed it:
        the fighters' own records share that event's batch."""
        self.run_it()

        gang.refresh_from_db()
        assert gang.open_visit.opened.kind == LedgerEvent.Kind.TRADE_POINTS_SET
        assert gang.open_visit.opened.note == "4"

    def test_it_stamps_the_purchases_that_counted(self, gang, mid_visit):
        self.run_it()

        gang.refresh_from_db()
        counted = mid_visit["counted"].ledger_entry
        counted.refresh_from_db()
        assert counted.action == gang.open_visit

    def test_it_leaves_a_purchase_that_counted_nothing_alone(self, gang, mid_visit):
        free = mid_visit["free"].ledger_entry
        self.run_it()

        free.refresh_from_db()
        assert free.action is None

    def test_what_is_left_reads_the_same_either_way(self, gang, mid_visit):
        self.run_it()

        gang.refresh_from_db()
        assert gang.trade_points_left == 1

    def test_running_it_again_changes_nothing(self, gang, mid_visit):
        self.run_it()
        gang.refresh_from_db()
        first = gang.open_visit

        self.run_it()

        gang.refresh_from_db()
        assert gang.open_visit.pk == first.pk
        assert gang.trade_points_left == 1

    def test_a_gang_with_no_visit_open_is_left_alone(self, gang, fighter, post):
        from n26.core.models import Action

        buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))

        self.run_it()

        assert not Action.objects.filter(
            gang=gang, kind=Action.Kind.TRADING_POST_VISIT
        ).exists()
