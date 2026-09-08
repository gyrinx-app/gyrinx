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
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

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


class TestAFighterIsNeverPricedBelowNothing:
    """Gear may be worth less than nothing; being hired never is. Nobody
    is paid to take a fighter on, so a negative there is an author's slip
    — and the floor has to hold on every surface that asks for the
    figure, not only the one the author happened to use."""

    def test_the_profile_form_refuses_it(self, make_profile):
        profile = make_profile("Juve")
        profile.price = -1
        with pytest.raises(ValidationError):
            profile.full_clean()

    def test_the_database_refuses_it_too(self, make_profile):
        """An importer never calls full_clean, so the floor cannot live
        in validation alone."""
        profile = make_profile("Juve")
        profile.price = -1
        with pytest.raises(IntegrityError), transaction.atomic():
            profile.save()

    def test_a_list_cannot_override_a_fighter_below_zero(self, default_pack, library):
        """The override is the same number asked for by a different
        surface, so it is floored the same way. Otherwise the rule would
        hold everywhere except where an author is likeliest to type it."""
        from n26.library.authoring import add_entry, create_collection

        hire_list = create_collection("Hangers-on")
        entry = add_entry(hire_list, library["bruiser"])
        # Set in memory and validated without saving: the constraint below
        # refuses the write outright, so the worded refusal has to be
        # reached before the database gets a chance to speak.
        entry.price_override = -50
        with pytest.raises(ValidationError):
            entry.full_clean()

    def test_the_database_refuses_that_override_too(self, default_pack, library):
        """The authoring verb and the ingest both make entries with
        ``objects.create``, so neither runs validation. Without the
        constraint the floor would hold only for whoever used a form."""
        from n26.library.authoring import add_entry, create_collection

        hire_list = create_collection("Hangers-on again")
        entry = add_entry(hire_list, library["bruiser"])
        entry.price_override = -50
        with pytest.raises(IntegrityError), transaction.atomic():
            entry.save()

    def test_a_list_may_still_override_gear_below_zero(self, default_pack, library):
        from n26.library.authoring import add_entry, create_collection

        gear_list = create_collection("Gene-smithing")
        entry = add_entry(gear_list, library["brittle_bones"], price_override=-20)
        entry.full_clean()
        assert entry.price.credits == -20
