"""Tests for the pure underdog / rating-spread derivation (Core Rulebook p238).

Deliberately DB-free — the whole point of ``handlers.underdog`` is that the
arithmetic is a pure function of the ratings, so none of these tests touch the
database or import a Django model. The DB-backed ``crew_spread_rating`` tests
(the cascade that produces the ratings fed in here) live in ``test_crew.py``,
next to the ``crew_setup`` / ``equipped_fighter`` fixtures they reuse.
"""

import pytest

from gyrinx.core.handlers.underdog import (
    STEP,
    UNDERDOG_THRESHOLD,
    compute_spread,
)


def _lower(gap, **kwargs):
    """The lower standing of a two-sided spread with a ``gap``-credit difference.

    Fixes the top side at 1000 and the other at ``1000 - gap`` so a single number
    drives each boundary case.
    """
    spread = compute_spread({"top": 1000, "low": 1000 - gap}, basis="crew", **kwargs)
    assert spread is not None
    lower = spread.standings[-1]  # sorted by rating desc, so the lower side is last
    assert lower.key == "low"
    return lower


# --- Steps and the underdog threshold ---------------------------------------


@pytest.mark.parametrize("gap", [0, 50, 99])
def test_sub_step_gaps_are_zero_steps_and_not_underdog(gap):
    s = _lower(gap)
    assert s.steps == 0
    assert s.is_underdog is False
    assert s.allowance == 0


@pytest.mark.parametrize("gap,steps", [(100, 1), (250, 2)])
def test_steps_below_threshold_grant_no_allowance(gap, steps):
    s = _lower(gap)
    assert s.steps == steps
    assert s.is_underdog is False
    assert s.allowance == 0


def test_threshold_is_inclusive():
    # A gap of exactly the threshold is an underdog.
    s = _lower(400)
    assert s.is_underdog is True
    assert s.steps == 4
    assert s.allowance == 400


def test_one_short_of_threshold_is_not_underdog():
    s = _lower(399)
    assert s.is_underdog is False
    assert s.steps == 3
    assert s.allowance == 0


def test_allowance_floors_a_partial_step():
    # 450¢ is four full steps, not five — the case a naive implementation rounds.
    s = _lower(450)
    assert s.is_underdog is True
    assert s.steps == 4
    assert s.allowance == 400


# --- Parameterisation -------------------------------------------------------


def test_custom_threshold_and_step_are_respected():
    # threshold 300, step 50: a 300 gap is 6 steps and an underdog.
    spread = compute_spread(
        {"top": 1000, "low": 700}, basis="gang", threshold=300, step=50
    )
    low = spread.standings[-1]
    assert low.steps == 6
    assert low.is_underdog is True
    assert low.allowance == 300

    # A 250 gap under the same rules: 5 steps but below the 300 threshold.
    spread = compute_spread(
        {"top": 1000, "low": 750}, basis="gang", threshold=300, step=50
    )
    low = spread.standings[-1]
    assert low.steps == 5
    assert low.is_underdog is False
    assert low.allowance == 0


def test_defaults_match_the_rulebook():
    assert UNDERDOG_THRESHOLD == 400
    assert STEP == 100


# --- Too few knowns, and excluded unknowns ----------------------------------


def test_single_rating_returns_none():
    assert compute_spread({"a": 500}, basis="crew") is None


def test_empty_returns_none():
    assert compute_spread({}, basis="crew") is None


def test_none_ratings_are_excluded():
    # One known side and one unknown leaves nothing to compare.
    assert compute_spread({"a": 500, "b": None}, basis="crew") is None


def test_unknowns_dropped_but_the_rest_still_compared():
    spread = compute_spread({"a": 500, "b": 300, "c": None}, basis="crew")
    assert spread is not None
    assert {s.key for s in spread.standings} == {"a", "b"}
    assert spread.top_rating == 500


# --- Multi-sided semantics --------------------------------------------------


def test_every_side_is_measured_against_the_top():
    # 1000 / 700 / 500 → gaps 0 / 300 / 500; only the 500 side clears 400.
    spread = compute_spread({"a": 1000, "b": 700, "c": 500}, basis="gang")
    by_key = {s.key: s for s in spread.standings}

    assert by_key["a"].gap == 0
    assert by_key["a"].is_underdog is False

    assert by_key["b"].gap == 300
    assert by_key["b"].steps == 3
    assert by_key["b"].is_underdog is False  # gets 3 extra tactics, not underdog

    assert by_key["c"].gap == 500
    assert by_key["c"].steps == 5
    assert by_key["c"].is_underdog is True
    assert by_key["c"].allowance == 500

    assert tuple(s.key for s in spread.underdogs) == ("c",)


def test_two_of_three_sides_can_both_be_underdogs():
    # Against a runaway leader, both trailing sides clear the threshold.
    spread = compute_spread({"a": 1200, "b": 700, "c": 600}, basis="gang")
    assert {s.key for s in spread.underdogs} == {"b", "c"}


def test_exact_tie_has_no_underdog():
    spread = compute_spread({"a": 600, "b": 600}, basis="crew")
    assert spread.top_rating == 600
    assert all(s.gap == 0 and s.steps == 0 for s in spread.standings)
    assert all(not s.is_underdog for s in spread.standings)
    assert spread.underdogs == ()


# --- Ordering ---------------------------------------------------------------


def test_standings_are_sorted_by_rating_descending():
    spread = compute_spread({"a": 300, "b": 900, "c": 600}, basis="gang")
    assert [s.rating for s in spread.standings] == [900, 600, 300]
    assert [s.key for s in spread.standings] == ["b", "c", "a"]


def test_ties_keep_insertion_order_deterministically():
    # Equal ratings preserve the order they were given in — a stable sort, so no
    # dependence on key comparability.
    forwards = compute_spread({"x": 500, "y": 500}, basis="crew")
    assert [s.key for s in forwards.standings] == ["x", "y"]
    backwards = compute_spread({"y": 500, "x": 500}, basis="crew")
    assert [s.key for s in backwards.standings] == ["y", "x"]


# --- Passthrough fields -----------------------------------------------------


def test_basis_and_provisional_are_recorded():
    spread = compute_spread({"a": 500, "b": 300}, basis="crew", provisional=True)
    assert spread.basis == "crew"
    assert spread.is_provisional is True

    default = compute_spread({"a": 500, "b": 300}, basis="gang")
    assert default.basis == "gang"
    assert default.is_provisional is False
