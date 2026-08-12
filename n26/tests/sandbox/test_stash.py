"""The stash: the gang's store of surplus equipment.

Rules facts this pins (core rules): the stash holds weapons and
wargear; gear moves freely between it and any number of models; Wealth
counts models, cash, and the stash. And the modelling decisions: the
stash is a **fourth assignment host** — acts like a model, needs no
profile, is never a card — and founding is unlimited spend: no budget
unless somebody sets one, the gang's number is its rating.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import browse
from n26.core.card import build_card
from n26.core.models import Assignment
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_ledger, build_model_card, render_gang
from n26.tests.sandbox.actions import (
    buy,
    create_collection,
    create_weapon,
    found_gang,
    hire_with_option,
    move,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(gang_type):
    return found_gang("The Bad Girls", gang_type, owner=User.objects.create_user("t"))


@pytest.fixture
def yolanda(gang, make_profile):
    return hire_with_option(gang, make_profile("Gang Queen", price=135), "Yolanda")


@pytest.fixture
def house_list(default_pack):
    return create_collection(
        "House List",
        entries=[
            (
                create_weapon("Lasgun", profiles=[("Standard", 0)]),
                {"price_override": 15},
            )
        ],
    )


def lasgun_line(house_list):
    return next(line for line in browse(house_list).all_lines())


class TestTheStore:
    def test_founding_creates_it(self, gang):
        assert gang.stash is not None
        assert gang.stash.rating == 0

    def test_founding_is_unlimited_spend(self, gang, yolanda):
        """No budget unless somebody sets one: the hire wrote an honest
        ledger line, nothing counted down, and the number is the rating."""
        assert gang.starting_credits is None
        gang.refresh_from_db()
        assert gang.credits == 0
        assert gang.rating == 135

    def test_buying_into_it_at_the_house_price(self, gang, house_list):
        """A forward-looking case, already expressible: the stash
        uses the gang's own list — a line is a complete purchase
        whoever the holder is."""
        bought = buy(gang.stash, lasgun_line(house_list))

        assert bought.stash == gang.stash
        assert bought.ledger_entry.paid == 15
        assert bought.ledger_entry.bought_from is not None
        gang.stash.refresh_from_db()
        assert gang.stash.rating == 15

    def test_a_stashed_weapon_keeps_its_profiles(self, gang, house_list):
        bought = buy(gang.stash, lasgun_line(house_list))
        assert bought.children.count() == 1  # the free profile rides along

    def test_stashed_gear_is_on_nobody_s_card(self, gang, yolanda, house_list):
        """The sharp edge: the stash shares the gang root with the
        broadcast rows, and must never ride onto a member's card."""
        buy(gang.stash, lasgun_line(house_list))

        card = build_card(yolanda, with_statlines=True)
        assert card.find("Lasgun") is None
        drawn = build_model_card(yolanda)
        assert drawn.weapons == []


class TestMoving:
    def test_to_a_model_and_onto_their_card(self, gang, yolanda, house_list):
        bought = buy(gang.stash, lasgun_line(house_list))
        move(bought, to=yolanda)

        drawn = build_model_card(yolanda)
        assert [w.name for w in drawn.weapons] == ["Lasgun"]
        assert drawn.weapons[0].profiles  # the subtree moved whole

    def test_the_rating_moves_pinned(self, gang, yolanda, house_list):
        """A move never re-prices: the 15 the stash counted is the 15
        the model counts."""
        bought = buy(gang.stash, lasgun_line(house_list))
        move(bought, to=yolanda)

        gang.refresh_from_db()
        gang.stash.refresh_from_db()
        yolanda.refresh_from_db()
        assert gang.stash.rating == 0
        assert yolanda.rating == 135 + 15
        assert gang.rating == 150

    def test_back_again(self, gang, yolanda, house_list):
        bought = buy(gang.stash, lasgun_line(house_list))
        move(bought, to=yolanda)
        move(bought, to=gang.stash)

        assert build_model_card(yolanda).weapons == []
        gang.stash.refresh_from_db()
        yolanda.refresh_from_db()
        assert gang.stash.rating == 15
        assert yolanda.rating == 135

    def test_the_ledger_remembers_every_move(self, gang, yolanda, house_list):
        bought = buy(gang.stash, lasgun_line(house_list))
        move(bought, to=yolanda, note="arming up")
        move(bought, to=gang.stash)

        view = build_ledger(gang)
        line = next(entry for entry in view.lines if entry.what == "Lasgun")
        assert [event.kind for event in line.events] == [
            "Purchased",
            "Moved",
            "Moved",
        ]

    def test_a_child_cannot_move_alone(self, gang, yolanda, house_list):
        bought = buy(gang.stash, lasgun_line(house_list))
        (profile_row,) = bought.children.all()
        with pytest.raises(Refusal, match="move that instead"):
            move(profile_row, to=yolanda)


class TestTheNumbers:
    def test_wealth_counts_models_cash_and_stash(self, gang, yolanda, house_list):
        buy(gang.stash, lasgun_line(house_list))
        gang.refresh_from_db()

        assert gang.rating == 135  # models only
        assert gang.stash.rating == 15
        assert gang.wealth == 135 + 0 + 15

    def test_gang_rating_never_counts_the_stash(self, gang, yolanda, house_list):
        buy(gang.stash, lasgun_line(house_list))
        gang.refresh_from_db()
        assert gang.rating == 135
        assert_reconciled(gang)

    def test_the_sheet_still_costs_a_fixed_number_of_queries(
        self, gang, make_profile, house_list
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        profile = make_profile("Ganger", price=50)
        hire_with_option(gang, profile, "One")
        # The first lasgun goes in before the first measurement: a
        # hydration pass only fires for kinds the rows name, so a fair
        # comparison grows what the stash already holds rather than
        # putting a weapon in it for the first time.
        buy(gang.stash, lasgun_line(house_list))

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert render_gang(gang).models
            return len(captured.captured_queries)

        few = measure()
        for index in range(3):
            hire_with_option(gang, profile, f"More {index}")
            buy(gang.stash, lasgun_line(house_list))
        assert measure() == few

    def test_a_ceiling_still_bites_when_set(self, gang_type, make_profile):
        """The budget did not vanish — it became opt-in. Set one, and
        overspend gets the same refusal as before."""
        from n26.core.operations import NotEnoughCredits

        gang = found_gang(
            "Broke", gang_type, owner=User.objects.create_user("b"), budget=100
        )
        with pytest.raises(NotEnoughCredits):
            hire_with_option(gang, make_profile("Matriarch", price=150), "Mags")


class TestNoDoubleCounting:
    def test_stash_rows_are_not_broadcast(self, gang, yolanda, house_list):
        """A stashed weapon must not become a carrier on every card —
        its modifiers belong to nobody until it is given to somebody."""
        buy(gang.stash, lasgun_line(house_list))
        card = build_card(yolanda)
        assert [node.name for node in card.all_nodes() if node.broadcast] == [
            str(gang.gang_type)
        ]

    def test_assignment_rows_say_where_things_live(self, gang, house_list):
        buy(gang.stash, lasgun_line(house_list))
        row = Assignment.objects.get(weapon__isnull=False)
        assert row.host == gang.stash
        assert row.gang_root == gang
        assert row.miniature_root is None
