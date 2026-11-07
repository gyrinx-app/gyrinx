"""A displayed equipment payment includes its selected option surcharge."""

import pytest

from n26.core.prices import BadPrice, price_typed


@pytest.mark.parametrize(
    "adjustment,raw,expected",
    [
        (15, "45", 45),
        (15, "15", 15),
        (-10, "-10", -10),
        (15, "100015", 100015),
        (-10, "99990", 99990),
        (15, "", 45),
    ],
)
def test_full_payments_use_the_same_base_bounds(adjustment, raw, expected):
    assert (
        price_typed({"paid": raw}, "paid", 30, "Harness", adjustment=adjustment)
        == expected
    )


@pytest.mark.parametrize(
    "adjustment,raw",
    [
        (15, "14"),
        (-10, "-11"),
        (15, "100016"),
        (-10, "99991"),
        (15, "1e2"),
        (15, "+45"),
        (15, "4.5"),
    ],
)
def test_out_of_range_or_non_whole_payments_are_rejected(adjustment, raw):
    with pytest.raises(BadPrice, match="whole number of credits"):
        price_typed({"paid": raw}, "paid", 30, "Harness", adjustment=adjustment)
