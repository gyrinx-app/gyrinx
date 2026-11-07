"""Template arithmetic accepts numeric strings; comparison filters use the bound when
a value cannot be parsed.
"""

import pytest

from n26.core.templatetags.arith import at_least, at_most, sub


class TestAtMost:
    """The price-input floor is the smaller of the quote and zero, for numbers and
    numeric strings.
    """

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
