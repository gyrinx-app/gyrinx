"""Presentation values for a sequence of forms and its final payment."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FlowStep:
    """One named step, with its position determined by the containing sequence."""

    label: str
    current: bool = False
    complete: bool = False
    href: str = ""


@dataclass(frozen=True)
class PaymentFigures:
    """A balance's reviewed figures, formatted by the caller."""

    label: str
    available: str
    price: str
    remaining: str
