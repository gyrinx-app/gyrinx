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
    move,
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


#: The entries each gang list holds, as ``(entry, the subtype naming its
#: rank)``. Shaped the way the books' lists are: a Venator gang's Hunters
#: are Specialists, an Outcast gang's Hive Scum is a Ganger and gets
#: nothing.
GANG_LISTS = {
    "Venators": [
        ("Hunt Leader", "Leader"),
        ("Hunt Champion", "Champion"),
        ("Hunter", "Specialist"),
    ],
    "Outcast": [
        ("Leader", "Leader"),
        ("Champion", "Champion"),
        ("Hive Scum", "Ganger"),
    ],
}

#: What a gang may also hire, whoever authored it: filed under a heading
#: of its own, and ranked the same way its own book ranks it.
ALLIES = [("Bone Scrivener", "Champion")]


@pytest.fixture
def ranks(default_pack):
    from n26.library.models import Subtype

    return {
        name: Subtype.objects.create(name=name)
        for name in ("Leader", "Champion", "Specialist", "Ganger")
    }


@pytest.fixture
def library(ranks, make_profile, make_statline):
    """Two gang lists and one allied entry, then the seed.

    The seed reads the library, so the entries are authored first: a
    gang's own list is what its founding figures name, and an ally ranked
    the same way is filed under its own heading and named by nobody.
    """
    from n26.library.authoring import add_built_in, create_category
    from n26.library.models import GangType
    from n26.library.standard_content import GANG_LIST_SECTION, STANDARD_CONTENT

    entries = {}

    def author(gang_type, section, name, rank):
        category = create_category(section, f"{gang_type.name} {rank} {section}")
        profile = make_profile(
            f"{gang_type.name} {name}", price=50, gang_type=gang_type, category=category
        )
        make_statline(profile)
        add_built_in(profile, ranks[rank])
        entries[(gang_type.name, name)] = profile

    for gang_type_name, rows in GANG_LISTS.items():
        gang_type = GangType.objects.create(name=gang_type_name)
        for name, rank in rows:
            author(gang_type, GANG_LIST_SECTION, name, rank)

    allies = GangType.objects.create(name="Allies")
    for name, rank in ALLIES:
        author(allies, "Allies", name, rank)

    STANDARD_CONTENT["founding-budgets"].create()
    return entries


@pytest.fixture
def budgets(library):
    """The seed, run over an authored library — named for what it grants
    rather than for what it reads."""
    return library


@pytest.fixture
def venators(library):
    from n26.library.models import GangType

    return GangType.objects.get(name="Venators")


@pytest.fixture
def outcast(library):
    from n26.library.models import GangType

    return GangType.objects.get(name="Outcast")


@pytest.fixture
def gang(venators, player):
    return found_gang("The Long Hunt", venators, owner=player, budget=1000)


@pytest.fixture
def hire_into(library):
    """Hire one of the library's entries into a gang, under a name, with
    any further subtypes assigned to the model itself."""

    def make(gang, entry, name, *rank_rows):
        gang_type, entry_name = entry
        model = hire_with_option(gang, library[(gang_type, entry_name)], name)
        for rank in rank_rows:
            assign(rank, miniature=model)
        return model

    return make


@pytest.fixture
def leader(gang, hire_into):
    return hire_into(gang, ("Venators", "Hunt Leader"), "Rasp")


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
    what the gang is affiliated with. It names the gang's own entries, so
    a model hired from somebody else's list reads nothing.
    """

    def test_a_venator_leader_may_spend_five(self, leader):
        assert reading(leader) == 5

    def test_a_venator_champion_may_spend_four(self, gang, hire_into):
        assert reading(hire_into(gang, ("Venators", "Hunt Champion"), "Kel")) == 4

    def test_a_venator_hunter_may_spend_three(self, gang, hire_into):
        """Every Venator Hunter entry is a Specialist, which is how the
        gang list marks the rank."""
        assert reading(hire_into(gang, ("Venators", "Hunter"), "Tuk")) == 3

    def test_an_outcast_hive_scum_may_spend_nothing(self, outcast, player, hire_into):
        """The Outcast book gives its Leaders and Champions a figure and
        nobody else one."""
        gang = found_gang("The Unhoused", outcast, owner=player, budget=1000)

        assert reading(hire_into(gang, ("Outcast", "Hive Scum"), "Nix")) == 0

    def test_an_ally_ranked_champion_may_spend_nothing(
        self, outcast, player, hire_into
    ):
        """A rank's subtype is carried right across the library, and an
        allied entry ranked Champion is nobody's Champion but their own.
        The figure names the gang's own entries, so hiring one in changes
        nothing about what it may spend."""
        gang = found_gang("The Unhoused", outcast, owner=player, budget=1000)

        hired = hire_into(gang, ("Allies", "Bone Scrivener"), "Aster")

        assert reading(hired) == 0

    def test_a_model_given_a_second_rank_still_spends_the_better_figure(
        self, gang, ranks, hire_into
    ):
        """The allowance is one allowance, so 5 and 4 do not come to 9.
        The figures name entries, and a Hunt Leader is one entry however
        many ranks are hung on the model."""
        both = hire_into(gang, ("Venators", "Hunt Leader"), "Rasp", ranks["Champion"])

        assert reading(both) == 5

    def test_a_clanless_gang_adds_one_more(self, outcast, player, hire_into):
        from n26.library.models import Affiliation
        from n26.library.standard_content import STANDARD_CONTENT

        clanless = Affiliation.objects.create(name="Clanless")
        STANDARD_CONTENT["founding-budgets"].create()
        gang = found_gang("The Unhoused", outcast, owner=player, budget=1000)
        assign(clanless, gang=gang)

        assert reading(hire_into(gang, ("Outcast", "Leader"), "Sura")) == 5
        assert reading(hire_into(gang, ("Outcast", "Champion"), "Nix")) == 4
        assert reading(hire_into(gang, ("Outcast", "Hive Scum"), "Tuk")) == 0

    def test_a_gang_whose_book_grants_none_reads_nothing(
        self, gang_type, player, library, hire_with_escher
    ):
        """Escher hands nobody an allowance, so its Leader has none."""
        escher = found_gang("The Wire", gang_type, owner=player, budget=1000)

        assert reading(hire_with_escher(escher, "Yolanda")) == 0


@pytest.fixture
def hire_with_escher(ranks, make_profile, make_statline):
    """A gang list nobody's founding figures name, ranked all the same."""

    def make(gang, name):
        from n26.library.authoring import add_built_in

        profile = make_profile("Escher Leader", price=50, gang_type=gang.gang_type)
        make_statline(profile)
        add_built_in(profile, ranks["Leader"])
        return hire_with_option(gang, profile, name)

    return make


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
        self, gang, leader, hire_into, legacy_list
    ):
        """The allowance belongs to the model, so what one has spent says
        nothing about what another may."""
        kel = hire_into(gang, ("Venators", "Hunt Champion"), "Kel")
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


class TestMovingWhatWasBought:
    """Spend follows the buyer, never the thing. Moving kit about is not
    a refund, and an owner who stashes a gun has not been handed its
    Trade Points back.
    """

    def test_stashing_it_does_not_hand_the_points_back(self, gang, leader, legacy_list):
        bought = buy_at_founding(
            leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
        )

        move(bought, gang.stash)

        assert budget(leader).spent == 3
        assert budget(leader).remaining == 2

    def test_handing_it_to_somebody_else_does_not_either(
        self, gang, leader, hire_into, legacy_list
    ):
        kel = hire_into(gang, ("Venators", "Hunt Champion"), "Kel")
        bought = buy_at_founding(
            leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
        )

        move(bought, kel)

        assert budget(leader).spent == 3
        assert budget(kel).spent == 0
        assert budget(kel).remaining == 4

    def test_and_refunding_it_there_returns_them_to_whoever_spent_them(
        self, gang, leader, hire_into, legacy_list
    ):
        """Otherwise the model it was handed to goes below zero for points
        it never spent, and the one who bought it never gets them back."""
        kel = hire_into(gang, ("Venators", "Hunt Champion"), "Kel")
        bought = buy_at_founding(
            leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
        )
        move(bought, kel)

        refund(bought)

        assert budget(leader).spent == 0
        assert budget(kel).spent == 0
        assert budget(kel).remaining == 4
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_tally_a_screen_draws_does_not_move(self, gang, leader, legacy_list):
        bought = buy_at_founding(
            leader, line_for(browse(legacy_list, FOUNDING), "Flak plate")
        )
        before = budget(leader).facts

        move(bought, gang.stash)

        assert budget(leader).facts == before


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
        self, gang, leader, hire_into, post
    ):
        """A model with no allowance buys against the visit, as it always
        did."""
        visit_trading_post(gang, brought=6)
        vesh = hire_into(gang, ("Allies", "Bone Scrivener"), "Vesh")

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
        """Matched by name, rewording one and running the seed again
        would hang a second contribution on the gang type and double what
        it grants."""
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
        before = sorted(raising.values_list("pk", flat=True))

        STANDARD_CONTENT["founding-budgets"].create()

        assert sorted(raising.values_list("pk", flat=True)) == before
        assert raising.count() == 3

    def test_an_entry_authored_later_shows_it_incomplete(
        self, budgets, venators, ranks, make_profile, make_statline
    ):
        """A new Hunt Leader entry is one nobody has given a figure to
        yet. Saying so is the point: the alternative is an entry that is
        quietly unbudgeted and nothing to show for it."""
        from n26.library.authoring import add_built_in, create_category
        from n26.library.standard_content import GANG_LIST_SECTION, STANDARD_CONTENT

        newcomer = make_profile(
            "Ogryn Hunt Leader",
            price=50,
            gang_type=venators,
            category=create_category(GANG_LIST_SECTION, "Venators Ogryn"),
        )
        make_statline(newcomer)
        add_built_in(newcomer, ranks["Leader"])

        present, wanted = STANDARD_CONTENT["founding-budgets"].check()
        assert present == wanted - 1

        STANDARD_CONTENT["founding-budgets"].create()

        assert STANDARD_CONTENT["founding-budgets"].check() == (wanted, wanted)

    def test_and_the_entry_is_named_by_the_modifier_already_standing(
        self, budgets, venators, ranks, make_profile, make_statline
    ):
        """Added to the one there rather than given a second: two
        modifiers granting the same figure would raise it twice."""
        from n26.library.authoring import add_built_in, create_category
        from n26.library.standard_content import (
            GANG_LIST_SECTION,
            STANDARD_CONTENT,
            founding_budget_counter,
        )

        newcomer = make_profile(
            "Ogryn Hunt Leader",
            price=50,
            gang_type=venators,
            category=create_category(GANG_LIST_SECTION, "Venators Ogryn"),
        )
        make_statline(newcomer)
        add_built_in(newcomer, ranks["Leader"])
        raising = venators.modifiers.filter(
            contributes_to_counter__counter=founding_budget_counter()
        )
        before = sorted(raising.values_list("pk", flat=True))

        STANDARD_CONTENT["founding-budgets"].create()

        assert sorted(raising.values_list("pk", flat=True)) == before
        named = raising.get(contributes_to_counter__amount=5).targets_miniature
        assert newcomer.pk in {
            profile.pk
            for row in named.is_profile.all()
            for profile in row.profiles.all()
        }

    def test_a_contribution_reaching_the_wrong_models_is_brought_round(
        self, budgets, venators, ranks
    ):
        """A figure that reached a rank rather than the gang's own entries
        would hand an allied Champion a Champion's allowance. The seed
        narrows the modifier already standing to the entries instead of
        making a second one, so nothing raises the figure twice."""
        from n26.library.authoring import (
            ef_contributes_to_counter,
            has_subtypes,
            recompose_modifier,
            targets_every_model,
        )
        from n26.library.standard_content import (
            STANDARD_CONTENT,
            founding_budget_counter,
        )

        counter = founding_budget_counter()
        raising = venators.modifiers.filter(contributes_to_counter__counter=counter)
        carried = raising.get(contributes_to_counter__amount=5)
        recompose_modifier(
            carried,
            carried.name,
            targets_every_model(has_subtypes(ranks["Leader"])),
            ef_contributes_to_counter(counter, 5),
        )
        present, wanted = STANDARD_CONTENT["founding-budgets"].check()
        assert present == wanted - 1

        STANDARD_CONTENT["founding-budgets"].create()

        assert STANDARD_CONTENT["founding-budgets"].check() == (wanted, wanted)
        assert raising.count() == 3

    def test_a_homebrew_gang_type_of_the_same_name_is_not_it(
        self, budgets, homebrew, ranks, make_profile, make_statline
    ):
        """Names are unique per pack, so somebody's own pack may hold a
        gang type called Venators. Its entries are not the standard
        list's and are given no figure."""
        from n26.library.authoring import add_built_in, create_category
        from n26.library.models import GangType, Subtype
        from n26.library.standard_content import (
            GANG_LIST_SECTION,
            STANDARD_CONTENT,
            founding_budget_counter,
        )

        theirs = GangType.objects.create(name="Venators", pack=homebrew)
        their_rank = Subtype.objects.create(name="Leader", pack=homebrew)
        their_entry = make_profile(
            "Their Hunt Leader",
            price=50,
            gang_type=theirs,
            pack=homebrew,
            category=create_category(GANG_LIST_SECTION, "Their Leaders", pack=homebrew),
        )
        make_statline(their_entry)
        add_built_in(their_entry, their_rank)

        STANDARD_CONTENT["founding-budgets"].create()

        assert not theirs.modifiers.filter(
            contributes_to_counter__counter=founding_budget_counter()
        ).exists()

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
