"""Verify Trade Points for trading-post visits: which collections charge them, how
purchases and refunds belong to a visit, and how contributions appear in receipts and
history. Visit allowances are derived from actions and ledger entries, not a second
pinned balance; see n26/design/collections.md. Credits remain the only enforced spending
limit.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import EQUIPMENT_LIST, TRADING_POST, browse, terms_for
from n26.core.models import Activity, LedgerEvent
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
    open_founding,
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
    return open_founding(
        found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
    )


@pytest.fixture
def fighter(gang, make_profile):
    return hire_with_option(gang, make_profile("Escher Ganger", price=55), "Yolanda")


@pytest.fixture
def kit(db):

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
    """Curated equipment list with the same items as the trading post."""
    listed = create_collection("Escher Equipment List")
    for thing in kit.values():
        add_entry(listed, thing)
    return listed


def line_for(view, name):
    return next(line for line in view.all_lines() if line.name == name)


class TestWhichSurfacesCharge:
    """Collection definitions determine buying terms. Trading-post selectors charge Trade
    Points; curated equipment lists charge only credits.
    """

    def test_a_post_swept_together_by_trade_point_prices_charges_them(self, post):
        assert terms_for(post) == TRADING_POST

    def test_a_list_an_author_wrote_out_by_hand_does_not(self, equipment_list):
        assert terms_for(equipment_list) == EQUIPMENT_LIST

    def test_a_browse_told_no_terms_uses_the_collections_own(self, post):

        assert all(line.charges_trade_points for line in browse(post).all_lines())

    def test_and_a_list_browsed_the_same_way_charges_nothing(self, equipment_list):
        assert not any(
            line.charges_trade_points for line in browse(equipment_list).all_lines()
        )

    def test_a_list_shows_the_figures_it_never_charges(self, gang, fighter, kit):
        """Listed Trade Point prices are informational when purchasing from an equipment
        list.
        """
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
        """Use None for no open visit, distinguishing it from an open visit with zero
        points.
        """
        assert gang.open_visit is None
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

        visit_trading_post(gang, brought=4)
        view = browse(equipment_list, EQUIPMENT_LIST)

        buy(fighter, line_for(view, "Mesh armour"))

        gang.refresh_from_db()
        assert gang.trade_points_left == 4

    def test_a_refund_on_the_same_trip_hands_the_points_back(self, gang, fighter, post):
        """A refund reverses both the credit and Trade Point entries for its purchase."""
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
        """Only one visit can be open, so a new purchase has an unambiguous activity to
        record.
        """
        from n26.core.operations import Refusal

        visit_trading_post(gang, brought=4)

        with pytest.raises(Refusal):
            visit_trading_post(gang, brought=4)

    def test_finishing_twice_ends_the_visit_once(self, gang):
        """Closing is idempotent: a repeated submission must not add another event or
        history entry.
        """
        from n26.core import history

        visit_trading_post(gang, brought=4)

        leave_trading_post(gang)
        leave_trading_post(gang)

        assert (
            LedgerEvent.objects.filter(
                gang=gang,
                kind=LedgerEvent.Kind.ACTION_CLOSED,
                note__startswith=Activity.Kind.TRADING_POST_VISIT,
            ).count()
            == 1
        )
        told = [
            act
            for act in history.build(gang)
            if "completed the Visit Trading Post action"
            in " ".join(span.text for span in act.spans)
        ]
        assert len(told) == 1

    def test_finishing_a_visit_nobody_opened_writes_nothing(self, gang):
        leave_trading_post(gang)

        assert not LedgerEvent.objects.filter(
            gang=gang,
            kind=LedgerEvent.Kind.ACTION_CLOSED,
            note__startswith=Activity.Kind.TRADING_POST_VISIT,
        ).exists()

    def test_what_went_before_stops_counting(self, gang, fighter, post):

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
        """Refunds follow the purchase's visit rather than their event time. Refunding
        older equipment must not increase the current allowance.
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
        """Equal allowances still require separate Activity rows. Reusing the previous
        visit would retain its spending.
        """
        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))
        gang.refresh_from_db()
        assert gang.trade_points_left == 3

        leave_trading_post(gang)
        visit_trading_post(gang, brought=4)

        gang.refresh_from_db()
        assert gang.trade_points_left == 4
        # Each visit has its own Activity row, independently of the allowance value.
        assert (
            Activity.objects.filter(
                gang=gang, kind=Activity.Kind.TRADING_POST_VISIT
            ).count()
            == 2
        )

    def test_the_visit_moves_no_money(self, gang):
        """Opening a visit changes neither credits nor rating."""
        before = gang.credits

        visit_trading_post(gang, brought=4)

        gang.refresh_from_db()
        assert gang.credits == before
        assert gang.rating == 0
        assert_reconciled(gang)


class TestOverspending:
    """Trade Point limits are advisory. Domain purchases may exceed the allowance or occur
    without an open visit.
    """

    def test_spending_past_the_allowance_goes_through(self, gang, fighter, post):
        visit_trading_post(gang, brought=1)
        view = browse(post, TRADING_POST)

        bought = buy(fighter, line_for(view, "Flak plate"))

        assert bought.ledger_entry.trade_points == 3
        gang.refresh_from_db()
        assert gang.trade_points_left == -2

    def test_buying_with_the_post_shut_goes_through_too(self, gang, fighter, post):
        """A purchase without an open visit still records its Trade Point price, but counts
        against no visit. The domain operation does not enforce visit eligibility.
        """
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))

        assert bought.ledger_entry.trade_points == 1
        gang.refresh_from_db()
        assert gang.visiting_trading_post is False
        assert gang.trade_points_left is None
        assert_reconciled(gang)


def only(gang, *names):
    """Select visitors by model name using the same roster derivation as the full offer."""
    chosen = {
        str(one.miniature.pk) for one in visitors(gang) if one.miniature.name in names
    }
    return visitors(gang, chosen)


@pytest.fixture
def ranks(default_pack):
    """Seed the hidden visit-contribution counter and its rank modifiers, so contributions
    come from authored content.
    """
    from n26.library.models import Subtype
    from n26.library.standard_content import STANDARD_CONTENT

    STANDARD_CONTENT["visit-contribution"].create()
    return {name: Subtype.objects.get(name=name) for name in ("Leader", "Champion")}


class TestWhoPerformsTheAction:
    """Record each contributor against their model and keep the total allowance on the
    visit action.
    """

    @pytest.fixture
    def ranked(self, gang, ranks, make_profile, make_statline):

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
        """The contributor picker omits zero-point fighters; equipment access has no
        equivalent restriction.
        """
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
        # Reuse the fixture's Champion subtype because names are unique within a pack.
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
        # The visit opening records the allowance once; contributor events must not
        # duplicate its delta.
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


class TestWhatARankAdds:
    """Derive contributions from effective counter values. Adding or removing ranks changes
    the figure through authored modifiers.
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
        """Derive contributions after removal assignments cancel their matching ranks."""
        rasp = hire_plain("Rasp")
        assign(ranks["Leader"], miniature=rasp)

        assign(ranks["Leader"], miniature=rasp, removes=True)

        assert self.offered(gang) == {}

    def test_a_model_holding_both_ranks_adds_the_better_figure(
        self, gang, ranks, hire_plain
    ):
        """The Champion modifier excludes Leaders, so holding both ranks contributes two
        points rather than three.
        """
        rasp = hire_plain("Rasp")
        assign(ranks["Leader"], miniature=rasp)
        assign(ranks["Champion"], miniature=rasp)

        assert self.offered(gang)["Rasp"].trade_points == 2

    def test_seeding_a_reworded_modifier_leaves_the_figure_alone(self, gang, ranks):
        """Match seeded contribution modifiers by effect rather than name, so renaming one
        cannot create a duplicate contribution.
        """
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
        """Group contributors by points rather than rank because different sources can
        contribute the same amount.
        """
        from n26.core.trading import as_offer

        assign(ranks["Leader"], miniature=hire_plain("Rasp"))
        assign(ranks["Champion"], miniature=hire_plain("Kel"))

        offer = as_offer(visitors(gang))

        assert [group.name for group in offer.groups] == [
            "2 Trade Points each",
            "1 Trade Point each",
        ]

    def test_a_library_with_no_counter_offers_nobody(self, gang, hire_plain):
        """A rank name alone contributes nothing without the seeded counter and modifiers."""
        from n26.library.models import Subtype

        assign(Subtype.objects.create(name="Leader"), miniature=hire_plain("Rasp"))

        assert visitors(gang) == []

    def test_what_the_visit_minted_is_what_the_ledger_says(
        self, gang, ranks, hire_plain
    ):
        """Read the receipt allowance from recorded visit state instead of recomputing
        current contributor values.
        """
        from n26.core.trading import minted

        assign(ranks["Leader"], miniature=hire_plain("Rasp"))
        assign(ranks["Champion"], miniature=hire_plain("Kel"))
        going = visitors(gang)

        visit_trading_post(gang, going)

        gang.refresh_from_db()
        assert minted(going) == 3
        assert gang.open_visit_brought == 3
        receipt = receipt_for(gang)
        assert (receipt.available, receipt.spent, receipt.remaining) == (3, 0, 3)
        assert receipt.summary == "Leader, Champion"
        assert_reconciled(gang)

    def test_the_figure_stays_a_fixed_number_of_queries(self, gang, ranks, hire_plain):
        """Query counts must stay constant as the roster grows. Include both rank types in
        the smaller fixture so only model count changes.
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


class TestAFigureInPlaceOfARank:
    """When several sources contribute, record the numeric figure and omit a rank label
    from history and receipt summaries.
    """

    @pytest.fixture
    def hire_plain(self, gang, make_profile, make_statline):
        def make(name):
            profile = make_profile(f"{name} entry", price=50)
            make_statline(profile)
            return hire_with_option(gang, profile, name)

        return make

    @pytest.fixture
    def connected(self, ranks):
        """Add an independent contribution to the rank counter, producing a figure with
        multiple sources.
        """
        from n26.library.standard_content import visit_contribution_counter
        from n26.tests.sandbox.actions import (
            create_rule,
            ef_contributes_to_counter,
            modifier,
            targets_model,
        )

        rule = create_rule("Well connected")
        modifier(
            "Well connected adds 1 Trade Point to a Trading Post visit",
            targets_model(),
            ef_contributes_to_counter(visit_contribution_counter(), 1),
            carried_by=rule,
        )
        return rule

    def sentences(self, gang):
        from n26.core import history

        return ["".join(span.text for span in act.spans) for act in history.build(gang)]

    def test_the_visit_records_the_figure(self, gang, ranks, connected, hire_plain):
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

    def test_the_history_says_only_that_they_went(
        self, gang, ranks, connected, hire_plain
    ):
        rasp = hire_plain("Rasp")
        assign(ranks["Leader"], miniature=rasp)
        assign(connected, miniature=rasp)
        visit_trading_post(gang, visitors(gang))

        (sent,) = [line for line in self.sentences(gang) if line.startswith("sent ")]

        assert sent == "sent Rasp to the trading post"

    def test_a_rank_still_leads_the_sentence(self, gang, ranks, hire_plain):
        """A single rank source keeps its rank label in history."""
        assign(ranks["Leader"], miniature=hire_plain("Rasp"))
        visit_trading_post(gang, visitors(gang))

        (sent,) = [line for line in self.sentences(gang) if line.startswith("sent ")]

        assert sent == "sent Rasp as Leader to the trading post"

    def test_the_receipt_leaves_the_figure_out_of_its_line(
        self, gang, ranks, connected, hire_plain
    ):
        rasp = hire_plain("Rasp")
        assign(ranks["Leader"], miniature=rasp)
        assign(connected, miniature=rasp)
        visit_trading_post(gang, visitors(gang))

        gang.refresh_from_db()
        receipt = receipt_for(gang)
        assert receipt.available == 3
        assert receipt.summary == ""

    def test_the_ranks_beside_it_are_still_named(
        self, gang, ranks, connected, hire_plain
    ):
        """A contributor with no single rank label must not hide other contributors' rank
        labels.
        """
        both = hire_plain("Rasp")
        assign(ranks["Leader"], miniature=both)
        assign(connected, miniature=both)
        assign(ranks["Champion"], miniature=hire_plain("Kel"))
        visit_trading_post(gang, visitors(gang))

        gang.refresh_from_db()
        assert receipt_for(gang).summary == "Champion"


class TestWhatTheHistorySays:
    """History shows Trade Points spent or refunded per purchase and unspent points
    discarded when a visit closes.
    """

    def sentences(self, gang):
        from n26.core import history

        return ["".join(span.text for span in act.spans) for act in history.build(gang)]

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
        """Internal event notes encode the allowance or closed state. Omit them from
        display because the history sentence already explains the action.
        """
        from n26.core import history

        visit_trading_post(gang, brought=4)
        leave_trading_post(gang)

        told = history.build(gang)[-2:]
        assert [act.note for act in told] == ["", ""]
        assert "closed" not in " ".join(span.text for act in told for span in act.spans)

    def test_opening_a_visit_spends_nothing(self, gang):
        """Opening records an allowance rather than a spending delta."""
        from n26.core import history

        visit_trading_post(gang, brought=4)

        opened = history.build(gang)[-1]
        assert opened.trade_points == 0
        assert opened.credits == 0

    def test_the_visit_says_what_it_set_out_with(self, gang):

        visit_trading_post(gang, brought=4)

        assert self.sentences(gang)[-1] == (
            "started the Visit Trading Post action with 4 Trade Points"
        )

    def test_one_point_is_one_point(self, gang):
        visit_trading_post(gang, brought=1)

        assert self.sentences(gang)[-1] == (
            "started the Visit Trading Post action with 1 Trade Point"
        )

    def test_a_visit_that_brought_none_says_so(self, gang):

        visit_trading_post(gang, brought=0)

        assert self.sentences(gang)[-1] == (
            "started the Visit Trading Post action with no Trade Points"
        )

    def test_finishing_says_what_the_book_took_away(self, gang, fighter, post):
        """Include discarded unspent points in the completion sentence."""
        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))

        leave_trading_post(gang)

        assert self.sentences(gang)[-1] == (
            "completed the Visit Trading Post action, discarding 1 unspent Trade Point"
        )

    def test_a_visit_that_spent_everything_loses_nothing(self, gang, fighter, post):

        visit_trading_post(gang, brought=3)
        buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))

        leave_trading_post(gang)

        assert self.sentences(gang)[-1] == "completed the Visit Trading Post action"

    def test_a_visit_that_overspent_loses_nothing_either(self, gang, fighter, post):

        visit_trading_post(gang, brought=1)
        buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))

        leave_trading_post(gang)

        assert self.sentences(gang)[-1] == "completed the Visit Trading Post action"

    def test_founding_carries_no_figure(self, gang, player):
        """Founding actions must not display trading-post allowances."""
        from n26.core.operations import operation

        with operation(gang, actor=player) as op:
            op.close_activity(gang.open_activity(Activity.Kind.FOUNDING))

        assert self.sentences(gang)[-1] == "completed the Spend founding TP action"


class TestWhatAPurchaseCountsAgainst:
    """Associate spending with the purchase's recorded visit, independently of event
    timestamps.
    """

    def test_a_purchase_at_the_post_records_the_open_visit(self, gang, fighter, post):
        visit_trading_post(gang, brought=4)

        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))

        gang.refresh_from_db()
        assert bought.ledger_entry.activity == gang.open_visit

    def test_a_purchase_from_a_list_records_nothing(
        self, gang, fighter, equipment_list
    ):
        """Equipment-list purchases are independent of an open visit because they charge no
        Trade Points.
        """
        visit_trading_post(gang, brought=4)

        bought = buy(
            fighter, line_for(browse(equipment_list, EQUIPMENT_LIST), "Mesh armour")
        )

        assert bought.ledger_entry.activity is None

    def test_a_purchase_with_the_post_shut_records_nothing(self, gang, fighter, post):
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))

        assert bought.ledger_entry.activity is None

    def test_what_an_action_spent_is_what_the_visit_spent(self, gang, fighter, post):

        from n26.core.reconcile import trade_points_spent_for

        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))

        gang.refresh_from_db()
        assert trade_points_spent_for(gang.open_visit) == 3
        assert gang.trade_points_spent == 3

    def test_a_refund_returns_the_points_to_the_action_that_paid(
        self, gang, fighter, post
    ):
        """Resolve the refund through its purchase assignment and original activity."""
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

    def test_a_purchase_naming_no_action_counts_against_none(self, gang, fighter, post):
        """Unassociated spending must not reduce a visit's allowance."""
        from n26.core.models import LedgerEntry

        visit_trading_post(gang, brought=4)
        bought = buy(fighter, line_for(browse(post, TRADING_POST), "Flak plate"))
        gang.refresh_from_db()
        assert gang.trade_points_spent == 3

        LedgerEntry.objects.filter(pk=bought.ledger_entry.pk).update(activity=None)

        gang.refresh_from_db()
        assert gang.trade_points_spent == 0
        assert gang.trade_points_left == 4

    def test_a_closed_action_still_says_what_it_spent(self, gang, fighter, post):
        """Keep historical visit totals readable after closure and subsequent visits."""
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


class TestReadingTheFigureOffTheGangsOwnRow:
    """Annotate the gang with its open visit allowance to avoid another query when
    displaying visit state. Remaining points require a separate ledger sum.
    """

    def fetched(self, gang):
        """Fetch the gang with the open_visit_points annotation used by view permission
        helpers.
        """
        from n26.core.models import Gang
        from n26.core.models.gang import open_visit_points

        return Gang.objects.annotate(open_visit_points=open_visit_points()).get(
            pk=gang.pk
        )

    def test_it_says_the_same_as_the_action_row(self, gang):
        visit_trading_post(gang, brought=4)

        gang.refresh_from_db()
        assert self.fetched(gang).open_visit_brought == gang.open_visit_brought == 4

    def test_a_visit_that_brought_nothing_is_still_a_visit(self, gang):
        """Zero means an open visit with no allowance; None means no open visit."""
        visit_trading_post(gang, brought=0)

        fetched = self.fetched(gang)
        assert fetched.open_visit_brought == 0
        assert fetched.visiting_trading_post is True
        assert fetched.trade_points_left == 0

    def test_a_shut_post_reads_as_nothing(self, gang):
        fetched = self.fetched(gang)
        assert fetched.open_visit_brought is None
        assert fetched.visiting_trading_post is False
        assert fetched.trade_points_left is None

    def test_drawing_the_figure_costs_no_query(self, gang, django_assert_num_queries):
        visit_trading_post(gang, brought=4)
        fetched = self.fetched(gang)

        with django_assert_num_queries(0):
            assert fetched.visiting_trading_post is True
            assert fetched.open_visit_brought == 4

    def test_what_is_left_costs_one(
        self, gang, fighter, post, django_assert_num_queries
    ):

        visit_trading_post(gang, brought=4)
        buy(fighter, line_for(browse(post, TRADING_POST), "Mesh armour"))
        fetched = self.fetched(gang)

        with django_assert_num_queries(1):
            assert fetched.trade_points_left == 3

    def test_forgetting_drops_it(self, gang):
        """Invalidate annotated visit state before an operation rechecks current
        activities.
        """
        visit_trading_post(gang, brought=4)
        fetched = self.fetched(gang)
        assert fetched.open_visit_brought == 4

        leave_trading_post(gang)
        fetched.forget_open_activities()

        assert fetched.open_visit_brought is None
        assert fetched.visiting_trading_post is False


def as_it_was(gang, brought, note=None):
    """Create a legacy TRADE_POINTS_SET event through the domain operation. Current visits
    use Activity rows, but existing boundary events must still render.
    """
    from n26.core.operations import operation

    with operation(gang, actor=gang.owner) as op:
        op.event(
            None,
            LedgerEvent.Kind.TRADE_POINTS_SET,
            note=str(brought) if note is None else note,
        )
    gang.refresh_from_db()


class TestWhatTheOlderHistorySays:
    """Preserve readable history for legacy visit boundary events without creating new
    ones.
    """

    def sentences(self, gang):
        from n26.core import history

        return ["".join(span.text for span in act.spans) for act in history.build(gang)]

    def test_an_old_visit_says_what_it_brought(self, gang):
        as_it_was(gang, brought=4)

        assert (
            self.sentences(gang)[-1] == "visited the Trading Post with 4 Trade Points"
        )

    def test_one_point_is_one_point(self, gang):
        as_it_was(gang, brought=1)

        assert self.sentences(gang)[-1] == "visited the Trading Post with 1 Trade Point"

    def test_a_boundary_carrying_no_figure_says_only_that_they_went(self, gang):
        as_it_was(gang, brought=0, note="")

        assert self.sentences(gang)[-1] == "visited the Trading Post"

    def test_an_old_visit_ends_with_the_word_a_new_one_ends_with(self, gang):
        """Legacy and Activity-based visits share the completion wording."""
        as_it_was(gang, brought=4)
        as_it_was(gang, brought=0, note="closed")

        assert self.sentences(gang)[-1] == "completed the Visit Trading Post action"

    def test_a_fighter_going_is_told_by_the_rank_they_went_as(self, gang, fighter):
        from n26.core.operations import operation

        with operation(gang, actor=gang.owner) as op:
            op.event(fighter, LedgerEvent.Kind.VISITED_TRADING_POST, note="Leader")

        assert self.sentences(gang)[-1] == (
            f"sent {fighter.name} as Leader to the trading post"
        )

    def test_a_bare_figure_leaves_the_rank_out(self, gang, fighter):
        """A numeric contribution does not identify a rank."""
        from n26.core.operations import operation

        with operation(gang, actor=gang.owner) as op:
            op.event(fighter, LedgerEvent.Kind.VISITED_TRADING_POST, note="3")

        assert self.sentences(gang)[-1] == f"sent {fighter.name} to the trading post"

    def test_none_of_these_notes_reach_the_page(self, gang):
        """Omit internal legacy event notes after using them to build the history sentence."""
        from n26.core import history

        as_it_was(gang, brought=4)
        as_it_was(gang, brought=0, note="closed")

        assert [act.note for act in history.build(gang)[-2:]] == ["", ""]
