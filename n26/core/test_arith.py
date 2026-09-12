"""The arithmetic filters, on the inputs a template really hands them.

A value reaches a filter as a string as often as a number — a component
attribute written without a colon is text — so each filter coerces before
it compares, and a value it cannot read yields its bound rather than an
error.
"""

import pytest

from n26.core.templatetags.arith import at_least, at_most, sub


class TestAtMost:
    """The least a price box may hold is the quote where the quote is
    below zero, and zero otherwise — read the same from a number or its
    text."""

    @pytest.mark.parametrize("quoted", [-10, "-10"])
    def test_a_quote_below_zero_is_the_floor(self, quoted):
        assert at_most(quoted, 0) == -10

    @pytest.mark.parametrize("quoted", [0, "0", 35, "35"])
    def test_a_quote_at_or_above_zero_floors_at_zero(self, quoted):
        assert at_most(quoted, 0) == 0

    def test_something_unreadable_yields_the_bound(self):
        assert at_most("", 0) == 0
        assert at_most(None, 0) == 0


class TestTheOthersStillCoerce:
    def test_at_least_from_text(self):
        assert at_least("2", 1) == 2

    def test_sub_from_text(self):
        assert sub("5", "2") == 3
