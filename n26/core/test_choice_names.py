"""How a several-pick slot writes what it holds.

No database — the line is a join of names, and a repeat is a count
beside the first of that name, written as the book writes a repeat:
``Enfeebled (x2)``. The picks stay as they were written.
"""

from types import SimpleNamespace

from n26.core.effects import ChoiceSlot, count_mark, stacked_names


def names(*held):
    return stacked_names(held)


class TestTheCountMark:
    """One rule for every surface that stacks repeats: nothing for one,
    the book's ``(xn)`` for more."""

    def test_one_reads_bare(self):
        assert count_mark(1) == ""

    def test_two_is_the_books_mark(self):
        assert count_mark(2) == " (x2)"

    def test_five_is_the_same_shape(self):
        assert count_mark(5) == " (x5)"


class TestStackedNames:
    def test_nothing_is_empty(self):
        assert names() == ""

    def test_one_name_is_the_name(self):
        assert names("Enfeebled") == "Enfeebled"

    def test_the_same_name_twice_is_counted(self):
        assert names("Enfeebled", "Enfeebled") == "Enfeebled (x2)"

    def test_five_of_one_is_counted(self):
        assert names(*["Enfeebled"] * 5) == "Enfeebled (x5)"

    def test_distinct_names_stay_in_order(self):
        assert names("Eye Injury", "Out Cold") == "Eye Injury, Out Cold"

    def test_a_later_repeat_joins_the_first_of_its_name(self):
        assert names("Enfeebled", "Out Cold", "Enfeebled") == "Enfeebled (x2), Out Cold"


def slot(*held):
    return ChoiceSlot(
        kind_label="Lasting Injuries",
        source="Ganger",
        source_kind="profile",
        anchor=None,
        picks=[SimpleNamespace(name=name) for name in held],
    )


class TestTheChosenLine:
    def test_no_picks_is_none(self):
        assert slot().chosen_name is None

    def test_repeats_read_as_a_count(self):
        assert (
            slot("Enfeebled", "Enfeebled", "Enfeebled").chosen_name == "Enfeebled (x3)"
        )


def cell(*sources, kinds=None):
    from n26.core.render import Provenance, StatCell

    kinds = kinds or [""] * len(sources)
    return StatCell(
        short_name="WS",
        full_name="Weapon Skill",
        value="6+",
        modified_by=[
            Provenance(source=source, source_kind=kind)
            for source, kind in zip(sources, kinds, strict=True)
        ],
    )


class TestTheTooltipSources:
    def test_repeats_read_as_a_count(self):
        assert cell(
            "Hand Injury", "Hand Injury", "Hand Injury", "Hand Injury"
        ).changed_by == ("Hand Injury (x4)")

    def test_a_kind_stays_on_the_name(self):
        assert (
            cell("Weapon Skill", kinds=["advancement"]).changed_by
            == "Weapon Skill (advancement)"
        )

    def test_the_held_note_is_separate(self):
        from n26.core.render import Provenance, StatCell

        held = StatCell(
            short_name="WS",
            full_name="Weapon Skill",
            value="6+",
            modified_by=[Provenance(source="Hand Injury")] * 4,
            held_at="minimum",
        )
        assert held.changed_by == "Hand Injury (x4)"
        assert held.held_note == "Cannot get any worse."

    def test_the_cells_draw_the_stacked_sentence(self):
        from django.template import Context, Template
        from django_cotton.compiler_regex import CottonCompiler

        from n26.core.render import Provenance, StatCell

        held = StatCell(
            short_name="WS",
            full_name="Weapon Skill",
            value="6+",
            modified_by=[Provenance(source="Hand Injury")] * 4,
            held_at="minimum",
        )
        html = Template(
            CottonCompiler().process('<c-n26.statline.cells :cells="cells" />')
        ).render(Context({"cells": [held]}))
        assert "WS changed by Hand Injury (x4). Cannot get any worse." in html
        assert "Hand Injury, Hand Injury" not in html
