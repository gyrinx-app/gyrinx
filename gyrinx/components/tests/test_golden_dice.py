"""Golden-equivalence test for the dice roller page."""

from __future__ import annotations

from itertools import zip_longest
from random import Random

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.views.dice import _dice_counts


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _build_context(request):
    """Reproduce the view's GET branch: parse the (untrusted) query string into
    bounded dice groups, deterministically rolling from ``seed`` when present."""
    mode = request.GET.get("m", "d6")
    d = _dice_counts(request, "d")
    fp = _dice_counts(request, "fp")
    i = _dice_counts(request, "i")
    if not (d or fp or i):
        d = [1]
    sides = {"d3": 3}.get(mode, 6)

    seed = request.GET.get("seed", "")
    rolled = bool(seed)
    rng = Random(seed) if rolled else None

    def roll(n, die_sides):
        if rng is None:
            return [None] * n
        return [rng.randint(1, die_sides) for _ in range(n)]

    groups = [
        dict(
            dice=roll(group[0], sides),
            firepower=roll(group[1], 6),
            injury=roll(group[2], 6),
            dice_n=group[0],
            firepower_n=group[1],
            injury_n=group[2],
        )
        for group in zip_longest(d, fp, i, fillvalue=0)
    ]

    # The view uses a random next_seed; a fixed one keeps the two renders that
    # assert_equivalent compares deterministic (both receive the same context).
    return {
        "mode": mode,
        "rolled": rolled,
        "next_seed": "1a2b3c4d",
        "groups": groups,
    }


@pytest.mark.django_db
def test_dice_rolled_matches_legacy(user):
    # Two groups (one with >1 die, one at the minimum) plus a seed, so the page
    # renders rolled dice faces, an enabled and a disabled group, and multi-value
    # query-string hrefs at nth 0 and 1.
    request = _request(user, "/dice/?m=d6&d=2&d=1&seed=deadbeef")
    context = _build_context(request)
    assert_equivalent("core/dice.html", context, request)


@pytest.mark.django_db
def test_dice_default_matches_legacy(user):
    # A bare visit: one group of a single (unrolled) die — exercises the
    # placeholder tray, the disabled/aria-disabled controls, and empty-GET hrefs.
    request = _request(user, "/dice/")
    context = _build_context(request)
    assert_equivalent("core/dice.html", context, request)


@pytest.mark.django_db
def test_dice_d3_mode_matches_legacy(user):
    # d3 mode toggles which Roll button is primary vs outline.
    request = _request(user, "/dice/?m=d3&d=3&seed=cafebabe")
    context = _build_context(request)
    assert_equivalent("core/dice.html", context, request)
