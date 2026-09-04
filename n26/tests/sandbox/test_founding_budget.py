"""Founding budgets: the Trade Points a model is given as it joins.

Some gang books hand a model a single allowance to spend as it is added
to the roster — a Venator Hunt Leader has 5 across the list its Gang
Legacy grants and the Trading Post together, an Outcast Champion 3, and
a Clanless gang's Leaders and Champions 1 more on top. The books call it
a combined figure, and combined is the whole of it: an equipment list
counts Trade Points here where nowhere else does.

Four claims, and each has a test below:

* what a model may spend is content — a counter its gang type and its
  affiliation raise — so nothing in the code names a rank or a figure,
  and a model holding two ranks spends the better and not the sum;
* what it has spent is what points back at the gang's Found and equip
  gang action, on that model alone;
* a refund returns to the action the purchase counted against, whenever
  it is taken, and a sale returns nothing;
* completing the action and starting it again gives a fresh figure,
  because spend is counted per action.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import FOUNDING, browse
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.founding import budget_for, budget_granted
from n26.core.models import Action
from n26.core.reconcile import assert_reconciled
from n26.tests.sandbox.actions import (
    add_entry,
    assign,
    buy,
    complete_action,
    create_collection,
    create_trading_post,
    create_wargear,
    found_gang,
    hire_with_option,
    refund,
    sell,
    start_action,
    visit_trading_post,
)

pytestmark = pytest.mark.django_db

FOUNDING_KIND = Action.Kind.FOUNDING


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def budgets(default_pack):
    """What the books grant, as content: the undrawn counter and the
    modifiers on each gang type and on the Clanless affiliation that
    raise it. Nothing in the code names a gang, a rank or a figure."""
    from n26.library.standard_content import STANDARD_CONTENT

    STANDARD_CONTENT["founding-budgets"].create()


@pytest.fixture
def ranks(budgets):
    from n26.library.models import Subtype

    return {
        name: Subtype.objects.get(name=name)
        for name in ("Leader", "Champion", "Specialist")
    }


@pytest.fixture
def venators(budgets):
    from n26.library.models import GangType

    return GangType.objects.get(name="Venators")


@pytest.fixture
def outcast(budgets):
    from n26.library.models import GangType

    return GangType.objects.get(name="Outcast")


@pytest.fixture
def gang(venators, player):
    return found_gang("The Long Hunt", venators, owner=player, budget=1000)


@pytest.fixture
def hire_into(make_profile, make_statline):
    """Hire a model of its own entry into any gang, at any rank."""

    def make(gang, name, *rank_rows):
        profile = make_profile(
            f"{name} entry",
            price=50,
            gang_type=gang.gang_type,
            pack=gang.gang_type.pack,
        )
        make_statline(profile)
        model = hire_with_option(gang, profile, name)
        for rank in rank_rows:
            assign(rank, miniature=model)
        return model

    return make


@pytest.fixture
def leader(gang, ranks, hire_into):
    return hire_into(gang, "Rasp", ranks["Leader"])


@pytest.fixture
def kit(db):
    """Two pieces of wargear, both priced in credits and in Trade Points,
    and one an equipment list alone stocks."""
    return {
        "mesh": create_wargear("Mesh armour", price=15, trade_point_price=1),
        "plate": create_wargear("Flak plate", price=40, trade_point_price=3),
        "relic": create_wargear("Hunt banner", price=20, is_exclusive=True),
    }


@pytest.fixture
def post(kit):
    return create_trading_post("Trading Post", contains=[type(kit["mesh"])])


@pytest.fixture
def legacy_list(kit):
    """The list a Gang Legacy grants, written out by hand."""
    listed = create_collection("House Escher Equipment List")
    for thing in kit.values():
        add_entry(listed, thing)
    return listed


def line_for(view, name):
    return next(line for line in view.all_lines() if line.name == name)


def reading(miniature):
    """What this model may spend, off its computed card."""
    card = build_card(miniature, with_options=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return budget_granted(compute(card, index))


def budget(miniature):
    card = build_card(miniature, with_options=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return budget_for(miniature.gang, miniature, compute(card, index))


def buy_at_founding(miniature, line, **kwargs):
    """Buy the way a budgeted model's equip screen buys: against the
    gang's open Found and equip gang action, whichever list the line
    came from."""
    return buy(
        miniature,
        line,
        action=miniature.gang.open_action(FOUNDING_KIND),
        **kwargs,
    )


class TestWhatTheBooksGrant:
    """The figure is a counter reading, raised by the gang type and by
    what the gang is affiliated with. A model in a gang whose book grants
    no such allowance reads nothing at all."""

    def test_a_venator_leader_may_spend_five(self, leader):
        assert reading(leader) == 5

    def test_a_venator_champion_may_spend_four(self, gang, ranks, hire_into):
        assert reading(hire_into(gang, "Kel", ranks["Champion"])) == 4

    def test_a_venator_hunter_may_spend_three(self, gang, ranks, hire_into):
        """Every Venator Hunter entry carries the Specialist subtype, and
        nothing else a Venator gang hires does."""
        assert reading(hire_into(gang, "Tuk", ranks["Specialist"])) == 3

    def test_a_model_with_no_rank_may_spend_nothing(self, gang, hire_into):
        assert reading(hire_into(gang, "Vesh")) == 0

    def test_a_model_holding_both_ranks_spends_the_better_figure(
        self, gang, ranks, hire_into
    ):
        """The allowance is one allowance, so 5 and 4 do not come to 9.
        The lesser rank's modifier is scoped away from models holding the
        better one, which is where that is settled."""
        both = hire_into(gang, "Rasp", ranks["Leader"], ranks["Champion"])

        assert reading(both) == 5

    def test_a_clanless_gang_adds_one_more(self, outcast, player, ranks, hire_into):
        from n26.library.models import Affiliation

        clanless = Affiliation.objects.create(name="Clanless")
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["founding-budgets"].create()
        gang = found_gang("The Unhoused", outcast, owner=player, budget=1000)
        assign(clanless, gang=gang)

        assert reading(hire_into(gang, "Sura", ranks["Leader"])) == 5
        assert reading(hire_into(gang, "Nix", ranks["Champion"])) == 4

    def test_a_gang_whose_book_grants_none_reads_nothing(
        self, gang_type, player, ranks, hire_into
    ):
        """Escher hands nobody an allowance, so its Leader has none —
        and neither does anybody hired into a gang of that type."""
        escher = found_gang("The Wire", gang_type, owner=player, budget=1000)

        assert reading(hire_into(escher, "Yolanda", ranks["Leader"])) == 0


class TestWhatCountsAgainstIt:
    """Every list counts here, which is the whole of "combined": the
    terms a budgeted model's screen browses on charge Trade Points
    wherever the line came from."""

    def test_an_equipment_list_line_counts_its_trade_points(self, legacy_list):
        assert all(
            line.charges_trade_points
            for line in browse(legacy_list, FOUNDING).all_lines()
        )

    def test_and_prints_them_where_it_never_would_otherwise(self, legacy_list):
        """A list an author wrote out prices in credits and leaves the TP
        figure off. A reader deciding against an allowance is asking for
        it, so the browse that counts them prints them."""
        plain = line_for(browse(legacy_list), "Flak plate")
        founding = line_for(browse(legacy_list, FOUNDING), "Flak plate")

        assert plain.shows_trade_points is False
        assert founding.shows_trade_points is True

    def test_an_exclusive_line_stays_on_the_listing(self, legacy_list):
        """An equipment list is exactly where an Exclusive item may be
        bought, so it is offered — and it carries no Trade Point figure,
        so it counts nothing."""
        line = line_for(browse(legacy_list, FOUNDING), "Hunt banner")

        assert line.is_exclusive is True
        assert line.trade_points is None

    def test_a_purchase_takes_it_off_the_model(self, gang, leader, legacy_list):
        bought = buy_at_founding(
            leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
        )

        assert bought.ledger_entry.trade_points == 3
        assert bought.ledger_entry.action == gang.open_action(FOUNDING_KIND)
        assert budget(leader).remaining == 2
        assert_reconciled(gang)

    def test_another_models_spending_is_not_this_ones(
        self, gang, leader, ranks, hire_into, legacy_list
    ):
        """The allowance belongs to the model, so what one has spent says
        nothing about what another may."""
        kel = hire_into(gang, "Kel", ranks["Champion"])
        buy_at_founding(leader, line_for(browse(legacy_list, FOUNDING), "Flak plate"))

        assert budget(leader).spent == 3
        assert budget(kel).spent == 0
        assert budget(kel).remaining == 4

    def test_a_weapons_paid_rounds_count_with_it(self, gang, leader, legacy_list):
        """A round hangs off the gun and not off the model, and it is
        still part of what the model spent."""
        mesh = line_for(browse(legacy_list, FOUNDING), "Mesh armour")
        plate = line_for(browse(legacy_list, FOUNDING), "Flak plate")
        buy_at_founding(leader, mesh)
        buy_at_founding(leader, plate)

        assert budget(leader).spent == 4
        assert budget(leader).remaining == 1

    def test_spending_past_it_is_allowed(self, gang, leader, legacy_list):
        """Trade Points inform; only credits are refused. Going past the
        allowance leaves it below zero."""
        for _ in range(2):
            buy_at_founding(
                leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
            )

        assert budget(leader).remaining == -1
        assert_reconciled(gang)


class TestGivingSomethingBack:
    """A refund follows the purchase; a sale returns nothing."""

    def test_a_refund_returns_to_the_founding_action(self, gang, leader, legacy_list):
        bought = buy_at_founding(
            leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
        )

        refund(bought)

        assert budget(leader).spent == 0
        assert budget(leader).remaining == 5
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_sale_returns_no_trade_points(self, gang, leader, legacy_list):
        """Selling is not undoing: the credits come back at half, and the
        Trade Points stay spent."""
        bought = buy_at_founding(
            leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
        )

        sell(bought)

        assert budget(leader).spent == 3
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_refund_after_the_action_closed_counts_against_nothing_open(
        self, gang, leader, legacy_list
    ):
        """The refund lands on the action the purchase counted against,
        which is complete. Starting again therefore begins at nothing
        spent rather than at points handed back into it."""
        bought = buy_at_founding(
            leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
        )
        complete_action(gang, FOUNDING_KIND)

        refund(bought)
        start_action(gang, FOUNDING_KIND)

        assert budget(leader).spent == 0
        assert budget(leader).remaining == 5
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestFinishingAndStartingAgain:
    """Spend is counted per action, so completing one and starting
    another gives the model its figure back whole. That is how an owner
    equips somebody hired after the founding was done."""

    def test_a_completed_action_leaves_no_budget(self, gang, leader):
        complete_action(gang, FOUNDING_KIND)

        assert budget(leader) is None

    def test_the_reading_stands_whatever_the_action_is_doing(self, gang, leader):
        """What a model may spend is its card's, not the action's: the
        allowance disappears because there is nothing open to spend it
        against, never because the figure changed."""
        complete_action(gang, FOUNDING_KIND)

        assert reading(leader) == 5

    def test_starting_again_begins_at_nothing_spent(self, gang, leader, legacy_list):
        buy_at_founding(leader, line_for(browse(legacy_list, FOUNDING), "Flak plate"))
        complete_action(gang, FOUNDING_KIND)

        start_action(gang, FOUNDING_KIND)

        assert budget(leader).spent == 0
        assert budget(leader).remaining == 5

    def test_the_earlier_actions_purchases_stay_on_it(self, gang, leader, legacy_list):
        first = buy_at_founding(
            leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
        )
        complete_action(gang, FOUNDING_KIND)
        start_action(gang, FOUNDING_KIND)

        assert first.ledger_entry.action != gang.open_action(FOUNDING_KIND)


class TestTwoAllowancesAtOnce:
    """The books do not open both at once, but nothing stops an owner
    doing it. The model's own points go first, and the gang's visit is
    left alone."""

    def test_a_founding_purchase_is_not_the_visits(
        self, gang, leader, post, legacy_list
    ):
        visit_trading_post(gang, brought=6)

        buy_at_founding(leader, line_for(browse(post), "Mesh armour"))

        gang.refresh_from_db()
        assert budget(leader).spent == 1
        assert gang.trade_points_left == 6

    def test_and_the_visits_purchases_are_not_the_models(
        self, gang, leader, ranks, hire_into, post
    ):
        """A model with no allowance buys against the visit, as it always
        did."""
        visit_trading_post(gang, brought=6)
        vesh = hire_into(gang, "Vesh")

        buy(vesh, line_for(browse(post), "Mesh armour"))

        gang.refresh_from_db()
        assert gang.trade_points_left == 5
        assert budget(leader).spent == 0


class TestTheSeed:
    """Standard content, created on demand: idempotent, matched by what a
    modifier does rather than by what it is called."""

    def test_it_reports_complete_once_run(self, budgets):
        from n26.library.standard_content import STANDARD_CONTENT

        present, wanted = STANDARD_CONTENT["founding-budgets"].check()
        assert present == wanted

    def test_running_it_again_creates_nothing(self, budgets):
        from n26.library.models import Modifier
        from n26.library.standard_content import (
            STANDARD_CONTENT,
            founding_budget_counter,
        )

        raising = Modifier.objects.filter(
            contributes_to_counter__counter=founding_budget_counter()
        )
        before = set(raising.values_list("pk", flat=True))

        STANDARD_CONTENT["founding-budgets"].create()

        assert set(raising.values_list("pk", flat=True)) == before

    def test_a_reworded_modifier_is_left_alone(self, budgets, venators):
        """Matched by name, rewording one and seeding again would hang a
        second contribution on the gang type and double what it grants."""
        from n26.library.standard_content import (
            STANDARD_CONTENT,
            founding_budget_counter,
        )

        raising = venators.modifiers.filter(
            contributes_to_counter__counter=founding_budget_counter()
        )
        carried = raising.get(contributes_to_counter__amount=5)
        carried.name = "Hunt Leaders get five"
        carried.save()

        STANDARD_CONTENT["founding-budgets"].create()

        assert list(raising.order_by("pk")) == list(raising.order_by("pk"))
        assert raising.count() == 3

    def test_an_affiliation_the_library_lacks_is_not_created(self, budgets):
        """Affiliations are authored content. A library without Clanless
        has no gang holding it either, so the seed leaves it out of the
        count rather than inventing the row."""
        from n26.library.models import Affiliation
        from n26.library.standard_content import STANDARD_CONTENT

        assert not Affiliation.objects.filter(name__iexact="Clanless").exists()
        present, wanted = STANDARD_CONTENT["founding-budgets"].check()
        assert (present, wanted) == (wanted, 6)

    def test_and_is_wired_up_the_moment_it_exists(self, budgets):
        from n26.library.models import Affiliation
        from n26.library.standard_content import (
            STANDARD_CONTENT,
            founding_budget_counter,
        )

        clanless = Affiliation.objects.create(name="Clanless")
        assert STANDARD_CONTENT["founding-budgets"].check() == (6, 7)

        STANDARD_CONTENT["founding-budgets"].create()

        assert STANDARD_CONTENT["founding-budgets"].check() == (7, 7)
        assert (
            clanless.modifiers.filter(
                contributes_to_counter__counter=founding_budget_counter()
            ).count()
            == 1
        )

    def test_the_counter_is_drawn_on_nothing(self, budgets):
        from n26.library.standard_content import founding_budget_counter

        assert founding_budget_counter().drawn is False

    def test_a_homebrew_counter_of_the_same_name_is_not_it(
        self, budgets, homebrew, gang, leader
    ):
        """Counter names are unique per pack, so a pack of somebody's own
        may hold one called this. It raises nothing here."""
        from n26.library.models import Counter
        from n26.library.standard_content import FOUNDING_BUDGET_COUNTER
        from n26.tests.sandbox.actions import (
            ef_contributes_to_counter,
            modifier,
            targets_model,
        )

        theirs = Counter.objects.create(name=FOUNDING_BUDGET_COUNTER, pack=homebrew)
        rule = create_wargear("Lucky charm", price=5, pack=homebrew)
        modifier(
            "Lucky charm raises somebody else's counter",
            targets_model(),
            ef_contributes_to_counter(theirs, 4),
            carried_by=rule,
        )
        assign(rule, miniature=leader)

        assert reading(leader) == 5
