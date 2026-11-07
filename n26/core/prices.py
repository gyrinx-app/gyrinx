"""Whole-credit payment input shared by hiring and equipment purchases."""

import re

from n26.errors import UserFacingError

PRICE_CEILING = 100_000
_WHOLE_CREDITS = re.compile(r"-?[0-9]+")


class BadPrice(UserFacingError):
    """A submitted price is outside the accepted whole-credit range."""


def price_floor(quoted):
    """Allow zero or the negative quoted price, whichever is lower."""
    return min(0, quoted)


def price_typed(data, field, quoted, name, *, adjustment=0):
    """Parse a whole-credit payment, retaining a blank field's quoted price.

    An adjustment includes selected equipment surcharges in the displayed payment
    while preserving the base payment's lower and upper bounds.
    """
    raw = data.get(field)
    if raw is None or not raw.strip():
        return quoted + adjustment
    raw = raw.strip()
    floor = price_floor(quoted) + adjustment
    ceiling = PRICE_CEILING + adjustment
    try:
        typed = int(raw) if _WHOLE_CREDITS.fullmatch(raw) else None
    except ValueError:
        typed = None
    if typed is None or not floor <= typed <= ceiling:
        raise BadPrice(
            f"{name}: a price is a whole number of credits, from {floor} to {ceiling}."
        )
    return typed
