"""The founding budget may not be exceeded (core rules).

The one place the operations layer rejects rather than informs: an
overspend raises a plain-language error at the operation boundary and the
whole transaction unwinds — previously it died as a database
IntegrityError when the credits pin went negative.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.models import Assignment, Miniature
from n26.core.operations import NotEnoughCredits
from n26.core.reconcile import assert_reconciled
from n26.tests.sandbox.actions import (
    buy,
    create_wargear,
    found_gang,
    hire_with_option,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(gang_type):
    player = User.objects.create_user("tom")
    return found_gang("The Bad Girls", gang_type, owner=player, budget=100)


class TestTheBudgetCeiling:
    def test_an_overspending_hire_is_refused_in_plain_language(
        self, gang, make_profile
    ):
        expensive = make_profile("Matriarch", price=150)

        with pytest.raises(NotEnoughCredits) as caught:
            hire_with_option(gang, expensive, "Yolanda")

        assert "50¢ short" in str(caught.value)
        assert "100¢ budget" in str(caught.value)

    def test_nothing_is_half_bought(self, gang, make_profile):
        """The refusal unwinds the whole operation."""
        expensive = make_profile("Matriarch", price=150)

        with pytest.raises(NotEnoughCredits):
            hire_with_option(gang, expensive, "Yolanda")

        assert Miniature.objects.count() == 0
        # The gang's founding survives; the refused hire wrote nothing.
        assert Assignment.objects.filter(gang_type__isnull=True).count() == 0
        gang.refresh_from_db()
        assert gang.credits == 100
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_an_overspending_purchase_is_refused_too(self, gang, make_profile):
        fighter = hire_with_option(gang, make_profile("Juve", price=90), "Sid")
        pricey = create_wargear("Gilded plate", price=25)

        with pytest.raises(NotEnoughCredits) as caught:
            buy(fighter, thing=pricey)

        assert "15¢ short" in str(caught.value)
        gang.refresh_from_db()
        assert gang.credits == 10
        assert_reconciled(gang)

    def test_spending_to_exactly_zero_is_fine(self, gang, make_profile):
        hire_with_option(gang, make_profile("Ganger", price=100), "Flush")
        gang.refresh_from_db()
        assert gang.credits == 0
        assert_reconciled(gang)
