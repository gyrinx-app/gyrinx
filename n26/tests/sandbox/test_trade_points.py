"""Trade Points: minted for a trip, spent at the post, lost at the end.

The rules give a gang Trade Points when its Leaders and Champions visit a
trading post — 2 a Leader, 1 a Champion — and take back whatever is left
when the visit ends. Credits are nothing like that: they are the gang's,
they persist, and spending past them is the one thing this edition
refuses.

So Trade Points are kept the other way round, per design/collections.md:
an allowance on the gang, and a sum over the ledger rather than a second
pinned figure. What makes a trip a trip is the allowance-set event — the
spending measured against an allowance is the spending recorded after it,
so setting one both opens a trip and closes the one before.

Four claims, and each has a test below:

* a list an author wrote out charges credits; a post swept together *by*
  Trade Point prices charges points as well;
* what is left is the allowance less the points the ledger records after
  it, and a refund on the same trip hands its points back;
* setting the allowance again wipes the slate, including setting it to
  the same figure;
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
    create_trading_post,
    create_wargear,
    found_gang,
    hire_with_option,
    leave_trading_post,
    refund,
    remove,
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

    def test_what_went_before_stops_counting(self, gang, fighter, post):
        """A second trip is measured from its own allowance. The first
        trip's spending is history, not a debt carried forward."""
        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))

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

    def test_setting_the_same_figure_is_a_second_trip_not_a_no_op(
        self, gang, fighter, post
    ):
        """The event is the boundary as much as the figure is, so a guard
        that skipped an unchanged write would leave the first trip's
        spending counting against the second."""
        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))
        gang.refresh_from_db()
        assert gang.trade_points_left == 3

        visit_trading_post(gang, brought=4)

        gang.refresh_from_db()
        assert gang.trade_points_left == 4
        assert (
            LedgerEvent.objects.filter(
                gang=gang, kind=LedgerEvent.Kind.TRADE_POINTS_SET
            ).count()
            == 2
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


@pytest.fixture
def ranks(default_pack):
    """What the ranks add, as content: the undrawn visit-contribution
    counter and the modifier on each rank that raises it. Nothing in the
    code names a rank or a figure."""
    from n26.library.models import Subtype
    from n26.library.standard_content import STANDARD_CONTENT

    STANDARD_CONTENT["visit-contribution"].create()
    return {name: Subtype.objects.get(name=name) for name in ("Leader", "Champion")}


class TestWhoPerformsTheAction:
    """Any fighter may go, and the two named ranks bring points with them.
    Who went is recorded per model, because the rules give each model one
    Post-cycle Action and a figure cannot say whose it was."""

    @pytest.fixture
    def ranked(self, gang, ranks, make_profile, make_statline):
        """A Leader, a Champion and a Ganger, each holding their rank."""
        made = {}
        for name, rank in [("Rasp", "Leader"), ("Kel", "Champion"), ("Tuk", None)]:
            profile = make_profile(f"{name} entry", price=50)
            make_statline(profile)
            model = hire_with_option(gang, profile, name)
            if rank:
                assign(ranks[rank], miniature=model)
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


class TestWhatARankAdds:
    """What a model adds is a counter reading, not a rank the code knows.

    The library holds an undrawn counter and a modifier on each rank that
    raises it, so the figure follows what a model *holds* — a fighter
    promoted into the rank adds it, one who has lost it adds nothing —
    and changing the figures is an authoring edit rather than a code
    change.
    """

    @pytest.fixture
    def hire_plain(self, gang, make_profile, make_statline):
        def make(name):
            profile = make_profile(f"{name} entry", price=50)
            make_statline(profile)
            return hire_with_option(gang, profile, name)

        return make

    def offered(self, gang):
        return {one.miniature.name: one for one in visitors(gang)}

    def test_a_model_promoted_into_a_rank_adds_what_the_rank_adds(
        self, gang, ranks, hire_plain
    ):
        rasp = hire_plain("Rasp")
        assert self.offered(gang) == {}

        assign(ranks["Leader"], miniature=rasp)

        assert self.offered(gang)["Rasp"].trade_points == 2

    def test_a_rank_taken_away_takes_the_figure_with_it(self, gang, ranks, hire_plain):
        rasp = hire_plain("Rasp")
        held = assign(ranks["Leader"], miniature=rasp)
        assert self.offered(gang)["Rasp"].trade_points == 2

        remove(held)

        assert self.offered(gang) == {}

    def test_a_rank_cancelled_by_a_removal_adds_nothing_either(
        self, gang, ranks, hire_plain
    ):
        """An owner's removal is machinery rather than a line, and the
        computed reading cancels the pair without anything here having to
        know it."""
        rasp = hire_plain("Rasp")
        assign(ranks["Leader"], miniature=rasp)

        assign(ranks["Leader"], miniature=rasp, removes=True)

        assert self.offered(gang) == {}

    def test_a_model_holding_both_ranks_adds_the_better_figure(
        self, gang, ranks, hire_plain
    ):
        """The same fighter cannot perform the action twice, so 2 and 1
        do not come to 3. The lesser rank's modifier is scoped away from
        models holding the better one, which is where that is settled."""
        rasp = hire_plain("Rasp")
        assign(ranks["Leader"], miniature=rasp)
        assign(ranks["Champion"], miniature=rasp)

        assert self.offered(gang)["Rasp"].trade_points == 2

    def test_seeding_a_reworded_modifier_leaves_the_figure_alone(self, gang, ranks):
        """The seed matches a rank's contribution by what it does, not by
        what it is called. Matched by name, rewording one and seeding
        again would hang a second contribution on the rank and double
        what it adds."""
        from n26.library.models import Modifier
        from n26.library.standard_content import STANDARD_CONTENT

        leaders = ranks["Leader"].modifiers.filter(contributes_to_counter__isnull=False)
        (carried,) = leaders
        carried.name = "Leader brings two"
        carried.save()

        STANDARD_CONTENT["visit-contribution"].create()

        assert list(leaders) == [carried]
        assert (
            Modifier.objects.filter(contributes_to_counter__isnull=False).count() == 2
        )

    def test_the_offer_is_grouped_by_the_figure(self, gang, ranks, hire_plain):
        """The heading says what the models under it add. Ranks are not
        what this knows, and two things may raise the reading by the same
        amount."""
        from n26.core.trading import as_offer

        assign(ranks["Leader"], miniature=hire_plain("Rasp"))
        assign(ranks["Champion"], miniature=hire_plain("Kel"))

        offer = as_offer(visitors(gang))

        assert [group.name for group in offer.groups] == [
            "2 Trade Points each",
            "1 Trade Point each",
        ]

    def test_a_library_with_no_counter_offers_nobody(self, gang, hire_plain):
        """No counter, no figure: the seed was never run here, so nothing
        on this roster adds Trade Points however it is ranked."""
        from n26.library.models import Subtype

        assign(Subtype.objects.create(name="Leader"), miniature=hire_plain("Rasp"))

        assert visitors(gang) == []

    def test_what_the_visit_minted_is_what_the_ledger_says(
        self, gang, ranks, hire_plain
    ):
        """The figure the ticks come to is the figure the visit opened
        with, and the receipt reads it back off the gang and the ledger
        rather than keeping a second copy of it."""
        from n26.core.trading import minted

        assign(ranks["Leader"], miniature=hire_plain("Rasp"))
        assign(ranks["Champion"], miniature=hire_plain("Kel"))
        going = visitors(gang)

        visit_trading_post(gang, going)

        gang.refresh_from_db()
        assert minted(going) == 3
        assert gang.starting_trade_points == 3
        receipt = receipt_for(gang)
        assert (receipt.available, receipt.spent, receipt.remaining) == (3, 0, 3)
        assert receipt.summary == "Leader, Champion"
        assert_reconciled(gang)

    def test_a_figure_two_things_raised_is_recorded_as_the_figure(
        self, gang, ranks, hire_plain
    ):
        """The visit records one name against each model. Where two
        things raised the reading no single name is true, so what goes on
        the record is the figure."""
        from n26.core.models import LedgerEvent
        from n26.library.models import Counter
        from n26.library.standard_content import VISIT_CONTRIBUTION_COUNTER
        from n26.tests.sandbox.actions import (
            create_rule,
            ef_contributes_to_counter,
            modifier,
            targets_model,
        )

        counter = Counter.objects.get(name=VISIT_CONTRIBUTION_COUNTER)
        connected = create_rule("Well connected")
        modifier(
            "Well connected adds 1 to a Trading Post visit",
            targets_model(),
            ef_contributes_to_counter(counter, 1),
            carried_by=connected,
        )
        rasp = hire_plain("Rasp")
        assign(ranks["Leader"], miniature=rasp)
        assign(connected, miniature=rasp)

        (one,) = visitors(gang)
        assert (one.trade_points, one.rank) == (3, "3")

        visit_trading_post(gang, [one])

        (went,) = LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.VISITED_TRADING_POST
        )
        assert went.note == "3"

    def test_the_figure_stays_a_fixed_number_of_queries(self, gang, ranks, hire_plain):
        """A whole gang is a fixed number of queries however many models
        are on it — the roster, the gang's own rows, and the modifiers
        those reach. Never a query per fighter.

        The count follows the *kinds* of content in play, not the size of
        the roster, so both readings below are taken with a Leader and a
        Champion already on it.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        assign(ranks["Leader"], miniature=hire_plain("Rasp"))
        assign(ranks["Champion"], miniature=hire_plain("Kel"))
        with CaptureQueriesContext(connection) as few:
            assert len(visitors(gang)) == 2

        for name in ("Tuk", "Vesh", "Mags", "Sura"):
            model = hire_plain(name)
            if name in ("Vesh", "Mags"):
                assign(ranks["Champion"], miniature=model)

        with CaptureQueriesContext(connection) as more:
            assert len(visitors(gang)) == 4

        assert len(more) == len(few)


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
