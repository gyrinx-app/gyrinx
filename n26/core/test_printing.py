"""Tests for the column split that CSS was supposed to do.

These matter more than most layout tests, because the behaviour they pin down
used to be a browser's and is now ours. When multicol did the balancing there
was nothing to assert; now there is, and a regression here is a card that reads
in the wrong order or a column that quietly claims half the width with nothing
in it.
"""

from dataclasses import dataclass

from n26.core.printing import balance_columns, detail_groups, estimate_lines
from n26.core.render import ChoiceLine, ModelCard, Statline


@dataclass(frozen=True)
class Group:
    label: str
    lines: int

    @property
    def height(self) -> int:
        return self.lines


def labels(columns):
    return [[group.label for group in column] for column in columns]


class TestEstimateLines:
    def test_short_text_is_one_line(self):
        assert estimate_lines("Spring Up", 30) == 1

    def test_text_wraps_at_the_column_width(self):
        assert estimate_lines("x" * 61, 30) == 3

    def test_an_empty_value_still_occupies_its_row(self):
        """A label with nothing after it is a line on the card either way."""
        assert estimate_lines("", 30) == 1

    def test_a_long_label_can_be_taller_than_its_value(self):
        """Labels beside their value wrap to one word per line, so the value
        keeps the width — two words is two lines whatever the value says."""
        assert estimate_lines("Ash", 30, label="Legendary Names") == 2


class TestBalanceColumns:
    def test_splits_at_the_point_that_evens_the_columns(self):
        groups = [Group("a", 3), Group("b", 1), Group("c", 1), Group("d", 3)]
        assert labels(balance_columns(groups)) == [["a", "b"], ["c", "d"]]

    def test_keeps_reading_order(self):
        """Groups are cut, never reordered. A reader scanning top to bottom and
        finding Gear before Skills has been lied to by the layout."""
        groups = [Group("a", 9), Group("b", 1), Group("c", 1)]
        columns = balance_columns(groups)
        assert [g.label for column in columns for g in column] == ["a", "b", "c"]

    def test_never_returns_an_empty_column(self):
        """Each column is a flex item claiming an equal share, so an empty one
        is not nothing — it is half the block, held open."""
        groups = [Group("a", 40), Group("b", 1)]
        assert all(balance_columns(groups))

    def test_a_tie_fills_the_first_column(self):
        """Matching column-major flow, which fills column one before spilling."""
        groups = [Group("a", 1), Group("b", 1), Group("c", 1), Group("d", 1)]
        assert labels(balance_columns(groups)) == [["a", "b"], ["c", "d"]]

    def test_one_group_stays_in_one_column(self):
        assert labels(balance_columns([Group("a", 5)])) == [["a"]]

    def test_nothing_gives_nothing(self):
        assert balance_columns([]) == []

    def test_three_columns(self):
        groups = [Group(c, 2) for c in "abcdef"]
        assert labels(balance_columns(groups, 3)) == [
            ["a", "b"],
            ["c", "d"],
            ["e", "f"],
        ]

    def test_fewer_groups_than_columns_gives_fewer_columns(self):
        """Better a two-column block than a three-column one with a hole in it."""
        assert labels(balance_columns([Group("a", 1), Group("b", 1)], 3)) == [
            ["a"],
            ["b"],
        ]

    def test_one_column_asked_for_is_one_column(self):
        groups = [Group("a", 1), Group("b", 1)]
        assert labels(balance_columns(groups, 1)) == [["a", "b"]]

    def test_a_dominant_group_does_not_drag_others_along(self):
        """The tall one is on its own; putting anything with it makes the split
        worse, and a greedy fill gets this wrong."""
        groups = [Group("a", 20), Group("b", 3), Group("c", 3), Group("d", 3)]
        assert labels(balance_columns(groups)) == [["a"], ["b", "c", "d"]]


def card_with(*choices):
    return ModelCard(
        name="Ozostium",
        rating=430,
        statline=Statline(),
        choices=list(choices),
    )


class TestDetailGroups:
    """What a printed card writes for its loose assignables.

    The column split is tested above; this is the words that go into it.
    """

    def test_a_partial_several_pick_prints_what_it_holds(self):
        """Paper cannot add another pick. The Add on the screen card is a
        way into the picker, and a printed card is read away from one."""
        card = card_with(
            ChoiceLine(
                kind_label="Lasting Injuries",
                chosen="Head Injury",
                takes_several=True,
                is_full=False,
            )
        )
        groups = detail_groups(card)
        assert [(group.label, group.text) for group in groups] == [
            ("Lasting Injuries", "Head Injury")
        ]

    def test_an_unresolved_choice_prints_as_a_blank(self):
        """An empty slot is a write-in on paper, not a prompt."""
        card = card_with(ChoiceLine(kind_label="Archetype", chosen=None))
        groups = detail_groups(card)
        assert [(group.label, group.text) for group in groups] == [("Archetype", "—")]
