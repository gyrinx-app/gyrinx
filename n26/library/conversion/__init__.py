"""Conversions that move a hand-built choice system onto slots and picks.

Each system's ``plan_*`` reads the database and returns a frozen Plan.
``apply`` performs exactly those steps, or refuses and unwinds.
"""

from n26.library.conversion.affiliation import plan_outcast_affiliation
from n26.library.conversion.base import ConversionRefused, Plan, apply

SYSTEMS = {
    "outcast_affiliation": plan_outcast_affiliation,
}

__all__ = [
    "ConversionRefused",
    "Plan",
    "SYSTEMS",
    "apply",
    "plan_outcast_affiliation",
]
