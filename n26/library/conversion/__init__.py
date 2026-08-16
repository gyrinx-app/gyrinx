"""Conversions — moving hand-built choice systems onto slots and picks.

Each system the content library built out of offers, hiddens and menu
collections is converted by one module here, through one discipline
(``base.py``): ``plan()`` reads the world and returns a frozen plan that
says everything it would do; ``apply(plan)`` performs exactly that in
one transaction and proves, before committing, that every affected
gang's pages still say the same things. The preview is the contract.
"""

from n26.library.conversion.base import ConversionRefused, Plan, apply
from n26.library.conversion.paths import plan_paths
from n26.library.conversion.specialisation import plan_specialisation

#: Every convertible system, by the name the command and the migrations
#: use. Ordered as the systems are meant to ship.
SYSTEMS = {
    "paths": plan_paths,
    "specialisation": plan_specialisation,
}

__all__ = [
    "ConversionRefused",
    "Plan",
    "SYSTEMS",
    "apply",
    "plan_paths",
    "plan_specialisation",
]
