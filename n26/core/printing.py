"""Partition print content into explicit columns before rendering HTML.

Nested CSS multi-column layouts are unreliable within printed pages,
including WebKit pagination. Compute deterministic groups by height so
templates can render ordinary side-by-side containers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from n26.core.rows import readable_parts, row_text


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
    parts: tuple = field(default=(), compare=False, repr=False)

    @property
    def height(self) -> int:
        return estimate_lines(self.text, self.chars_per_line, self.label)


def _item_choices(lines) -> list[DetailGroup]:
    """A carried item's non-tier questions, labelled with the item that carries them."""
    return [
        DetailGroup(
            f"{line.name} — {row.label}",
            row_text(row),
            parts=tuple(readable_parts(row)),
        )
        for line in lines
        for row in line.other_choice_rows
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
    groups = [
        DetailGroup(
            row.label,
            text,
            parts=tuple(readable_parts(row, skip_xp=hasattr(card, "statline"))),
        )
        for row in card.detail_rows
        if (text := row_text(row, skip_xp=hasattr(card, "statline")))
    ]
    groups.extend(
        DetailGroup(
            row.label,
            row_text(row, skip_xp=False),
            parts=tuple(readable_parts(row, skip_xp=False)),
        )
        for row in getattr(card, "owned_choice_rows", ())
    )
    groups.extend(_item_choices(getattr(card, "equipment", ())))
    for group in getattr(card, "gear_groups", ()):
        groups.extend(_item_choices(group.lines))
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

    Choose ``columns - 1`` cut points that minimise the tallest column. Keeping
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
