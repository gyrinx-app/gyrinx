"""Conversions that move a hand-built choice system onto slots and picks.

Each system's ``plan_*`` reads the database and returns a frozen Plan.
``apply`` performs exactly those steps, or refuses and unwinds.
"""

from n26.library.conversion.affiliation import plan_outcast_affiliation
from n26.library.conversion.base import ConversionRefused, Plan, apply
from n26.library.conversion.chaos_god import plan_chaos_god
from n26.library.conversion.variant import plan_variant

SYSTEMS = {
    "outcast_affiliation": plan_outcast_affiliation,
    "chaos_god": plan_chaos_god,
    "variant": plan_variant,
}

__all__ = [
    "ConversionRefused",
    "Plan",
    "SYSTEMS",
    "apply",
    "plan_chaos_god",
    "plan_outcast_affiliation",
    "plan_variant",
]
