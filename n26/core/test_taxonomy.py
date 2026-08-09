"""Filing rows under the catalogue's headings.

Two surfaces group this way — a shopping list and the gang list you hire
from — and each has its own containers and its own idea of what order
rows take. So the rules are checked here, once, on stand-ins: no gang, no
content rows, no database. What a heading and a category need is a name
and a position, and that is all these carry.
"""

from dataclasses import dataclass, field

from n26.core.taxonomy import group_by_home


@dataclass(frozen=True)
class Heading:
    name: str
    position: int


@dataclass(frozen=True)
class Home:
    name: str
    position: int
    section: Heading


@dataclass(frozen=True)
class Row:
    name: str
    weight: int = 0


@dataclass
class DrawnCategory:
    name: str
    rows: list = field(default_factory=list)


@dataclass
class DrawnSection:
    name: str
    categories: list = field(default_factory=list)


def grouped(*homed_rows):
    return group_by_home(
        homed_rows,
        section=lambda name, categories: DrawnSection(name=name, categories=categories),
        category=lambda name, rows: DrawnCategory(name=name, rows=rows),
        order=lambda row: (row.weight, row.name),
    )


def shape(sections):
    """What was drawn, as plain names — the whole answer in one literal."""
    return [
        (
            section.name,
            [
                (category.name, [row.name for row in category.rows])
                for category in section.categories
            ],
        )
        for section in sections
    ]


ranged = Heading("Ranged Weapons", 0)
close = Heading("Close Combat Weapons", 1)


class TestTheOrderThingsCome:
    def test_headings_take_their_own_positions(self):
        pistols = Home("Pistols", 1, ranged)
        blades = Home("Blades", 0, close)

        assert shape(grouped((blades, Row("Knife")), (pistols, Row("Stub gun")))) == [
            ("Ranged Weapons", [("Pistols", ["Stub gun"])]),
            ("Close Combat Weapons", [("Blades", ["Knife"])]),
        ]

    def test_categories_take_theirs_within_a_heading(self):
        basic = Home("Basic", 1, ranged)
        pistols = Home("Pistols", 0, ranged)

        assert shape(grouped((basic, Row("Autogun")), (pistols, Row("Stub gun")))) == [
            ("Ranged Weapons", [("Pistols", ["Stub gun"]), ("Basic", ["Autogun"])])
        ]

    def test_rows_take_the_order_the_caller_asked_for(self):
        pistols = Home("Pistols", 0, ranged)

        drawn = grouped(
            (pistols, Row("Stub gun", weight=2)),
            (pistols, Row("Autopistol", weight=1)),
        )
        assert shape(drawn) == [
            ("Ranged Weapons", [("Pistols", ["Autopistol", "Stub gun"])])
        ]


class TestOneHeadingIsDrawnOnce:
    """A heading drawn twice is a tab drawn twice, and a strip keys its
    tabs by name — so one of the pair shows the other's rows and the
    other becomes unreachable, while a reader meets the same heading
    again further down the page holding different things."""

    def test_categories_that_would_alternate_still_gather(self):
        # Positions are the whole taxonomy's, so one heading's categories
        # can straddle another's.
        early = Home("Pistols", 0, ranged)
        middle = Home("Blades", 1, close)
        late = Home("Basic", 2, ranged)

        assert shape(
            grouped(
                (early, Row("Stub gun")),
                (middle, Row("Knife")),
                (late, Row("Autogun")),
            )
        ) == [
            ("Ranged Weapons", [("Pistols", ["Stub gun"]), ("Basic", ["Autogun"])]),
            ("Close Combat Weapons", [("Blades", ["Knife"])]),
        ]

    def test_two_headings_of_one_name_are_one_section_placed_earliest(self):
        """A heading's name is unique within a pack and nowhere else, so
        two packs each naming one "Ranged Weapons" is how this arises."""
        theirs = Heading("Ranged Weapons", 2)
        ours = Home("Pistols", 0, ranged)
        borrowed = Home("Bounty weapons", 9, theirs)
        between = Home("Blades", 1, close)

        assert shape(
            grouped(
                (ours, Row("Stub gun")),
                (between, Row("Knife")),
                (borrowed, Row("Bolt pistol")),
            )
        ) == [
            (
                "Ranged Weapons",
                [("Pistols", ["Stub gun"]), ("Bounty weapons", ["Bolt pistol"])],
            ),
            ("Close Combat Weapons", [("Blades", ["Knife"])]),
        ]


class TestWhatIsKeptApart:
    def test_one_category_name_under_two_headings_stays_two_categories(self):
        """A category name is only unique within its heading — the
        rulebook has Esoteric weapons under both Ranged and Close
        combat — so matching on the string would fold two into one."""
        one = Home("Esoteric", 0, ranged)
        other = Home("Esoteric", 1, close)

        assert shape(grouped((one, Row("Web gun")), (other, Row("Shock stave")))) == [
            ("Ranged Weapons", [("Esoteric", ["Web gun"])]),
            ("Close Combat Weapons", [("Esoteric", ["Shock stave"])]),
        ]

    def test_a_homeless_row_gathers_at_the_end_under_no_heading(self):
        """A content gap to show, not an error to hide. What the empty
        heading is called on screen is the drawing surface's business."""
        pistols = Home("Pistols", 0, ranged)

        assert shape(grouped((None, Row("Oddment")), (pistols, Row("Stub gun")))) == [
            ("Ranged Weapons", [("Pistols", ["Stub gun"])]),
            ("", [("", ["Oddment"])]),
        ]

    def test_nothing_at_all_draws_nothing(self):
        assert grouped() == []
