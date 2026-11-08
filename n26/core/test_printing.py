"""Printed card columns balance estimated group heights without changing reading
order or allocating empty columns.
"""

from dataclasses import dataclass

from n26.core.printing import balance_columns, detail_groups, estimate_lines
from n26.core.render import AssignableLine, ChoiceLine, EffectLine, ModelCard, Statline


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
        """An empty value still occupies one labelled line."""
        assert estimate_lines("", 30) == 1

    def test_a_long_label_can_be_taller_than_its_value(self):
        """Estimate one line per label word when the label shares horizontal space
        with a value.
        """
        assert estimate_lines("Ash", 30, label="Legendary Names") == 2


class TestBalanceColumns:
    def test_splits_at_the_point_that_evens_the_columns(self):
        groups = [Group("a", 3), Group("b", 1), Group("c", 1), Group("d", 3)]
        assert labels(balance_columns(groups)) == [["a", "b"], ["c", "d"]]

    def test_keeps_reading_order(self):
        """Split contiguous groups without reordering them."""
        groups = [Group("a", 9), Group("b", 1), Group("c", 1)]
        columns = balance_columns(groups)
        assert [g.label for column in columns for g in column] == ["a", "b", "c"]

    def test_never_returns_an_empty_column(self):
        """Empty flex columns would reserve unused space in the print layout."""
        groups = [Group("a", 40), Group("b", 1)]
        assert all(balance_columns(groups))

    def test_a_tie_fills_the_first_column(self):
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
        assert labels(balance_columns([Group("a", 1), Group("b", 1)], 3)) == [
            ["a"],
            ["b"],
        ]

    def test_one_column_asked_for_is_one_column(self):
        groups = [Group("a", 1), Group("b", 1)]
        assert labels(balance_columns(groups, 1)) == [["a", "b"]]

    def test_a_dominant_group_does_not_drag_others_along(self):
        """Keep the dominant group alone when adding another group would worsen the
        balance.
        """
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
    """Printed detail groups show current content without interactive picker prompts."""

    def test_a_partial_several_pick_prints_what_it_holds(self):
        """Print existing picks without the on-screen Add prompt, which cannot be
        used on paper.
        """
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
        """An unresolved choice leaves a write-in blank on paper."""
        card = card_with(ChoiceLine(kind_label="Archetype", chosen=None))
        groups = detail_groups(card)
        assert [(group.label, group.text) for group in groups] == [("Archetype", "—")]

    def test_an_item_tier_prints_beside_its_name_without_a_separate_group(self):
        card = card_with()
        card.equipment = [
            AssignableLine(
                name="Hunting rig",
                choices=[
                    ChoiceLine(
                        kind_label="Augmentation",
                        chosen="Tier 2",
                        is_tier_ladder=True,
                    ),
                    ChoiceLine(kind_label="Colour", chosen=None),
                ],
            )
        ]

        assert [(group.label, group.text) for group in detail_groups(card)] == [
            ("Gear", "Hunting rig (Tier 2)"),
            ("Hunting rig — Colour", "—"),
        ]

    def test_an_empty_item_tier_adds_no_printed_group(self):
        card = card_with()
        card.equipment = [
            AssignableLine(
                name="Hunting rig",
                choices=[
                    ChoiceLine(
                        kind_label="Augmentation",
                        chosen=None,
                        is_tier_ladder=True,
                    )
                ],
            )
        ]

        assert [(group.label, group.text) for group in detail_groups(card)] == [
            ("Gear", "Hunting rig")
        ]

    def test_stored_effect_prose_is_not_printed(self):
        """Print the resulting state in its dedicated location rather than the stored
        operation description.
        """
        card = card_with()
        card.effects = [EffectLine("marks the model In Recovery", happened=True)]

        assert detail_groups(card) == []
