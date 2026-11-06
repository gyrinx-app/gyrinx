"""Partition print content into explicit columns before rendering HTML.

Nested CSS multi-column layouts are unreliable within printed pages,
including WebKit pagination. Compute deterministic groups by height so
templates can render ordinary side-by-side containers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class HasHeight(Protocol):
    """Anything that can estimate how many lines it will take."""

    @property
    def height(self) -> int: ...


@dataclass(frozen=True)
class DetailGroup:
    """A labelled run of text, sized well enough to balance columns with.

    The height is an estimate and openly so — it ranks two candidate splits
    against each other, and being out by a line only matters in a case that
    was already near-balanced.
    """

    label: str
    text: str

    #: Measured line capacity for a half-width card column at 2.4mm type.
    chars_per_line: int = 30

    @property
    def height(self) -> int:
        return estimate_lines(self.text, self.chars_per_line, self.label)


def _run(lines) -> str:
    """A run of names: one that brought a pet written with the pet's
    name, one standing for several written with its count — in that
    order, as the screen card writes them."""
    return ", ".join(
        line.name + line.tier_mark + line.brought_mark + line.count_mark
        for line in lines
    )


def _item_choices(lines) -> list[DetailGroup]:
    """A carried item's non-tier questions, labelled with the item that carries them."""
    return [
        DetailGroup(f"{line.name} — {choice.kind_label}", choice.chosen or "—")
        for line in lines
        for choice in line.other_choices
    ]


def detail_groups(card) -> list[DetailGroup]:
    """Group card details into labelled runs for printing.

    Include unresolved choices as blanks and selected item tiers beside names.
    Omit equipment collections, which describe application purchase access.
    Omit XP counter lines because XP already appears in the statline.

    Do not repeat stored effects as prose: their current results appear in
    status, counter or pet displays, and the original operation can disagree
    with later state changes.
    """
    groups = []
    for counter in card.counter_lines:
        # XP already appears in the statline; paper needs no separate update control.
        if not counter.is_xp:
            groups.append(DetailGroup(counter.name, str(counter.value)))
    # A line standing for several of one thing is written once with its
    # count, as the screen card writes it.
    if card.skills:
        groups.append(DetailGroup("Skills", _run(card.skills)))
    if card.rules:
        groups.append(DetailGroup("Rules", _run(card.rules)))
    if card.powers:
        groups.append(DetailGroup("Powers", _run(card.powers)))
    if card.equipment:
        groups.append(DetailGroup("Gear", _run(card.equipment)))
        groups.extend(_item_choices(card.equipment))
    for gear_group in card.gear_groups:
        # Under the category's own name, as on screen. A group with
        # nothing in it is not built, so there is no empty one to skip.
        groups.append(DetailGroup(gear_group.name, _run(gear_group.lines)))
        groups.extend(_item_choices(gear_group.lines))
    for choice in card.row_questions:
        # Print selected values or a blank. Item-owned choices print beside
        # the item rather than in these general details.
        groups.append(DetailGroup(choice.kind_label, choice.chosen or "—"))
    return groups


def detail_columns(card, columns: int = 2) -> list[list[DetailGroup]]:
    return balance_columns(detail_groups(card), columns)


def estimate_lines(text: str, chars_per_line: int, label: str = "") -> int:
    """How many lines ``text`` will take in a column ``chars_per_line`` wide.

    A rough count, and rough is the right target: this feeds a choice between
    two splits, so it needs to rank them, not to predict a renderer. Being out
    by a line moves a group between columns in a case that was near-balanced
    anyway.

    ``label`` is counted because a label set beside its value wraps to its
    narrowest — one word per line, so the value keeps the width — and a
    two-word label on a one-line value is two lines tall, not one.
    """
    body_lines = -(-len(text) // chars_per_line) if text else 0
    return max(1, body_lines, len(label.split()))


def balance_columns[T: HasHeight](groups: list[T], columns: int = 2) -> list[list[T]]:
    """Split groups into non-empty columns in their existing reading order.

    Choose columns minus one cuts that minimise the tallest column. Keeping
    contiguous groups preserves top-to-bottom reading order; omitting empty
    columns avoids reserving unused horizontal space.
    """
    if columns < 2 or len(groups) <= 1:
        return [groups] if groups else []

    heights = [group.height for group in groups]

    # Check every cut position: cards have few groups, and greedy cuts
    # can leave visibly uneven columns.
    best: list[list[T]] | None = None
    best_tallest = None

    def search(start: int, remaining: int, cuts: list[int]) -> None:
        nonlocal best, best_tallest
        if remaining == 1:
            bounds = [0, *cuts, len(groups)]
            split = [groups[a:b] for a, b in zip(bounds, bounds[1:], strict=False)]
            if any(not column for column in split):
                return
            tallest = max(
                sum(heights[a:b]) for a, b in zip(bounds, bounds[1:], strict=False)
            )
            # `<=` rather than `<`: on a tie prefer the later cut, which fills
            # the earlier column first and matches how column-major flow reads.
            if best_tallest is None or tallest <= best_tallest:
                best, best_tallest = split, tallest
            return
        for cut in range(start + 1, len(groups) - remaining + 2):
            search(cut, remaining - 1, [*cuts, cut])

    search(0, columns, [])

    # Fewer groups than columns: there is no split that leaves none empty, so
    # give one group per column and stop short of the requested count.
    if best is None:
        return [[group] for group in groups]
    return best
