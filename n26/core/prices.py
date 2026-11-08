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


def price_typed(data, field, quoted, name):
    """Parse a whole-credit payment, retaining a blank field's quoted price."""
    raw = data.get(field)
    if raw is None or not raw.strip():
        return quoted
    raw = raw.strip()
    floor = price_floor(quoted)
    typed = int(raw) if _WHOLE_CREDITS.fullmatch(raw) else None
    if typed is None or not floor <= typed <= PRICE_CEILING:
        raise BadPrice(
            f"{name}: a price is a whole number of credits, "
            f"from {floor} to {PRICE_CEILING}."
        )
    return typed
