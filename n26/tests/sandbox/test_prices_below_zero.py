"""Things priced below nothing.

Most of what a gang buys makes it worth more. A few things do the
opposite: a Goliath Gene-smithing upgrade that weakens the fighter is
priced in negative credits, and taking it makes the model cheaper to
recruit and worth less on the roster.

The ledger has always been signed, so what this proves is that a
below-zero price survives the whole way through — the catalogue, the
purchase, the gang's credits, the rating — and that the one place it
could have leaked, the floor under a sale, does not pay a gang for
shedding a liability.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.operations import proceeds_for
from n26.core.reconcile import assert_reconciled
from n26.tests.sandbox.actions import (
    assign,
    create_wargear,
    found_gang,
    hire,
    refund,
    sell,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("player")


@pytest.fixture
def library(default_pack, person_type, gang_type, make_profile):
    return {
        "bruiser": make_profile("Goliath Bruiser", price=100),
        # The weakening upgrade: it takes credits off what the fighter is
        # worth rather than adding them.
        "brittle_bones": create_wargear("Reduced bone density", price=-10),
        "plating": create_wargear("Dermal hardening", price=10),
    }


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Chain", gang_type, owner=player, budget=1000)


class TestABelowZeroPrice:
    def test_the_catalogue_keeps_the_sign(self, library):
        assert library["brittle_bones"].price == -10
        assert library["brittle_bones"].reference_price() == -10

    def test_buying_one_gives_the_gang_credits_back(self, gang, library, player):
        mini = hire(gang, library["bruiser"], "Krath", paid=100)
        before = gang.credits
        assign(library["brittle_bones"], miniature=mini, paid=-10)
        gang.refresh_from_db()
        assert gang.credits == before + 10

    def test_it_takes_the_model_below_the_profile_price(self, gang, library):
        mini = hire(gang, library["bruiser"], "Krath", paid=100)
        assign(library["brittle_bones"], miniature=mini, paid=-10)
        gang.refresh_from_db()
        assert gang.rating == 90

    def test_it_still_reconciles(self, gang, library):
        mini = hire(gang, library["bruiser"], "Krath", paid=100)
        assign(library["brittle_bones"], miniature=mini, paid=-10)
        assert_reconciled(gang)

    def test_one_of_each_cancels_out(self, gang, library):
        mini = hire(gang, library["bruiser"], "Krath", paid=100)
        assign(library["brittle_bones"], miniature=mini, paid=-10)
        assign(library["plating"], miniature=mini, paid=10)
        gang.refresh_from_db()
        assert gang.rating == 100
        assert_reconciled(gang)


class TestGivingOneBack:
    def test_refunding_it_takes_the_credits_away_again(self, gang, library):
        """A refund undoes the purchase whichever way the money went. The
        gang was paid to take this on, so handing it back has a price."""
        mini = hire(gang, library["bruiser"], "Krath", paid=100)
        held = assign(library["brittle_bones"], miniature=mini, paid=-10)
        gang.refresh_from_db()
        paid_up = gang.credits
        refund(held)
        gang.refresh_from_db()
        assert gang.credits == paid_up - 10
        assert gang.rating == 100
        assert_reconciled(gang)

    def test_selling_it_pays_nothing(self, gang, library):
        """The floor under a sale would otherwise pay a gang five credits
        every time it dropped something worth less than nothing."""
        mini = hire(gang, library["bruiser"], "Krath", paid=100)
        held = assign(library["brittle_bones"], miniature=mini, paid=-10)
        gang.refresh_from_db()
        before = gang.credits
        sell(held)
        gang.refresh_from_db()
        assert gang.credits == before
        assert_reconciled(gang)


class TestTheFloorIsOtherwiseUnchanged:
    def test_something_worth_nothing_still_fetches_the_floor(self):
        assert proceeds_for(0) == 5

    def test_something_cheap_still_fetches_the_floor(self):
        assert proceeds_for(4) == 5

    def test_something_dear_fetches_half_rounded_up(self):
        assert proceeds_for(45) == 23

    def test_something_worth_less_than_nothing_fetches_nothing(self):
        assert proceeds_for(-10) == 0
