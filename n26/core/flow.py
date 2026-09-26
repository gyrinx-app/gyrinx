"""Presentation values for a sequence of forms and its final payment."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FlowStep:
    """One named step, with its position determined by the containing sequence.

    ``skipped`` is a step this run of the flow will not take. It keeps its
    place and number so the steps after it do not renumber.
    """

    label: str
    current: bool = False
    complete: bool = False
    href: str = ""
    skipped: bool = False


@dataclass(frozen=True)
class PaymentFigures:
    """A balance's reviewed figures, formatted by the caller."""

    label: str
    available: str
    price: str
    remaining: str
