"""The nested ticks a checkbox card holds, as data its React island draws."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckboxCardItem:
    """One nested checkbox: what it posts, what it says, and an optional figure.

    The island draws these rows, and makes them inert while the card's own
    box is clear. Inert still posts: leave an item out, or have the view
    ignore it, if it must not submit with the card clear.
    """

    name: str
    value: str
    label: str
    checked: bool = False
    meta: str = ""
