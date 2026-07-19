"""Rating-spread / underdog derivation (Core Rulebook p238).

Pure, DB-free arithmetic. Given each side's rating, work out the gap to the
strongest side, how many full-``step`` bands of difference that is, whether the
side is the Underdog, and the optional credit allowance. No Django, no models,
no I/O: the inputs are opaque caller keys mapped to integer ratings, so the same
evaluator can serve the crew page, the battle page, and any future "campaign gap
rules" feature.

The rulebook: scenarios compare either the credits value of the fighters in each
starting crew or the Gang Rating. For each full 100¢ the lower side is behind,
it draws an extra gang tactic (no threshold). From a 400¢ gap the lower side is
the **Underdog**, and an optional arbitrator variant converts those tactics into
a credit allowance of 100¢ per full 100¢ of gap.

``threshold`` and ``step`` are arguments, defaulting to the rulebook values —
the evaluator takes no position on which mechanic a campaign plays with. Only
fighters ever enter the comparison; extras (tactics cards, hired help) do not,
so callers pass fighter ratings, never a crew's full credits value.
"""

from dataclasses import dataclass
from typing import Any, Optional

# Rulebook defaults (Core Rulebook p238); callers may override — the evaluator
# takes no position on which mechanic a campaign plays with.
UNDERDOG_THRESHOLD = 400
STEP = 100


@dataclass(frozen=True)
class Standing:
    """One side's position in the spread, relative to the strongest side."""

    key: Any  # opaque caller key (e.g. a gang id)
    rating: int
    gap: int  # top_rating - rating; 0 for the top side
    steps: int  # gap // step — full bands ("100s") of difference
    is_underdog: bool  # gap >= threshold
    allowance: int  # steps * step when is_underdog, else 0


@dataclass(frozen=True)
class Spread:
    """The whole comparison: every side's standing, plus a few conveniences."""

    standings: tuple[Standing, ...]  # ordered by rating desc
    top_rating: int
    basis: str  # "crew" | "gang" — caller-supplied label for what was compared
    is_provisional: bool  # any input was a forecast, so the spread may still move
    underdogs: tuple[Standing, ...]  # the standings with is_underdog, same order


def compute_spread(
    ratings,
    *,
    basis,
    provisional=False,
    threshold=UNDERDOG_THRESHOLD,
    step=STEP,
) -> Optional[Spread]:
    """Derive the spread from ``ratings`` (a mapping of caller key → rating).

    Every side is measured against the **highest** rating present, so with three
    or more sides two of them can both be underdogs — our documented reading;
    RAW only covers two sides. ``gap // step`` floors (a 450¢ gap is 4 steps and
    a 400¢ allowance, never rounded up), and the underdog ``threshold`` is
    inclusive (a gap of exactly the threshold is an underdog). An exact tie
    yields zero steps and no underdog for both.

    A ``None`` rating is a side whose figure isn't known yet (e.g. a crew whose
    random draw hasn't resolved); such sides are excluded from the comparison
    entirely. Returns ``None`` when fewer than two ratings are known — there is
    nothing to compare.

    ``basis`` labels what was compared (crew credits value vs Gang Rating) and
    ``provisional`` records that at least one input was a forecast; both are
    passed straight through onto the :class:`Spread`. Ties in rating keep their
    insertion order in ``ratings`` (a stable sort), so the result is
    deterministic without requiring the keys to be orderable.
    """
    known = [(key, rating) for key, rating in ratings.items() if rating is not None]
    if len(known) < 2:
        return None

    top_rating = max(rating for _, rating in known)

    # Highest rating first; the stable sort leaves equal ratings in insertion
    # order, so we never have to compare (possibly unorderable) keys.
    ordered = sorted(known, key=lambda kv: -kv[1])

    standings = []
    for key, rating in ordered:
        gap = top_rating - rating
        steps = gap // step
        is_underdog = gap >= threshold
        standings.append(
            Standing(
                key=key,
                rating=rating,
                gap=gap,
                steps=steps,
                is_underdog=is_underdog,
                allowance=steps * step if is_underdog else 0,
            )
        )

    standings = tuple(standings)
    return Spread(
        standings=standings,
        top_rating=top_rating,
        basis=basis,
        is_provisional=bool(provisional),
        underdogs=tuple(s for s in standings if s.is_underdog),
    )
