"""Layout decisions that have to be made before the HTML is.

Printing is the one place where a renderer cannot leave layout to CSS, because
the CSS that would do the job does not survive being printed. The clearest case
is multi-column text: WebKit has no support for a multi-column container nested
inside another fragmentation context, and when printing, the page *is* a
fragmentation context — so iOS Safari collapses a two-column block to one
full-width column, and the layout exists on the developer's desktop and nowhere
else. Chrome fails at it more quietly, by dropping the last group off the end.

So the split is done here, in Python, and the template renders two plain boxes
that any engine can lay out. It is deterministic, identical everywhere, and —
unlike a CSS behaviour observed in one browser — something a test can assert.

Nothing here knows about HTML. It takes things with a height and returns them
grouped, which is all a column is.
"""

from __future__ import annotations

from typing import Protocol


class HasHeight(Protocol):
    """Anything that can estimate how many lines it will take."""

    @property
    def height(self) -> int: ...


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
    """Split ``groups`` across ``columns``, keeping them in reading order.

    Groups are cut at ``columns - 1`` points, exactly as column-major flow
    would: the first column takes the first N, the next takes the following
    ones, and so on. Reading order is preserved because a reader who scans a
    card top-to-bottom and finds Skills after Gear has been lied to by the
    layout, and no amount of balance is worth that.

    The cut minimises the tallest column, which is what multicol's balancing
    was doing before it stopped working on paper.

    An empty column is never returned. Each column is a flex item claiming an
    equal share of the width, so an empty one is not nothing — it is a third of
    the block, held open, and the content beside it mysteriously narrow.
    """
    if columns < 2 or len(groups) <= 1:
        return [groups] if groups else []

    heights = [group.height for group in groups]

    # Exhaustive over cut positions. With a handful of groups on a card this is
    # a few dozen combinations at most, and being exact is worth more than being
    # clever — a greedy fill gets the near-balanced cases visibly wrong.
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
