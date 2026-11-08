"""Preserve negative equipment prices through purchase, credits and rating calculations.
Refunding reverses the payment, while selling negative-rated equipment yields no
proceeds.
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
        # Negative-priced upgrades reduce the model's rating.
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
        """Refund the original signed payment: returning negatively priced gear removes the
        credits received on purchase.
        """
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
        """Bypass the ordinary minimum sale proceeds for negative ratings."""
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
    """Require non-negative fighter prices in both model validation and database
    constraints, including collection overrides.
    """

    def test_the_profile_form_refuses_it(self, make_profile):
        profile = make_profile("Juve")
        profile.price = -1
        with pytest.raises(ValidationError):
            profile.full_clean()

    def test_the_database_refuses_it_too(self, make_profile):
        """Protect direct saves that bypass full_clean."""
        profile = make_profile("Juve")
        profile.price = -1
        with pytest.raises(IntegrityError), transaction.atomic():
            profile.save()

    def test_a_list_cannot_override_a_fighter_below_zero(self, default_pack, library):
        """Apply the fighter price floor to collection-specific overrides during model
        validation.
        """
        from n26.library.authoring import add_entry, create_collection

        hire_list = create_collection("Hangers-on")
        entry = add_entry(hire_list, library["bruiser"])
        # Call full_clean without saving to check the validation message before database
        # enforcement.
        entry.price_override = -50
        with pytest.raises(ValidationError):
            entry.full_clean()

    def test_the_database_refuses_that_override_too(self, default_pack, library):
        """Protect authoring and ingest writes that create collection entries without
        calling full_clean.
        """
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
